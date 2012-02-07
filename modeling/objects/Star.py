# -*- coding: utf-8 -*-

"""
Module including functions for stellar parameters, and the STAR class and 
its methods and attributes.

Author: R. Lombaert

"""

import types
from glob import glob
import os
from scipy import pi, log, sqrt
from scipy import array, exp
from scipy import integrate, linspace
from scipy import argmin,argmax
import operator

from cc.data import Data
from cc.tools.io import Database
from cc.tools.io import DataIO
from cc.tools.numerical import Interpol
from cc.modeling.objects import Molecule
from cc.modeling.objects import Transition
from cc.modeling.tools import ColumnDensity

  

def powerRfromT(T,T_STAR,R_STAR=1.0,power=0.5):
    
    """
    Inverse of a T-power law.
    
    Returns the radius in the same units as R_STAR, if given.
    
    If not given, R is given in stellar radii.
       
    @param T: temperature for which radius is calculated assuming a power law:
              T = T_STAR * (R_STAR/R)**(power)
    @type T: float or array
    @param T_STAR: stellar effective temperature
    @type T_STAR: float or array
    
    @keyword R_STAR: stellar radius, default for a returned value in stellar
                     radii
                     
                     (default: 1.0)
    @type R_STAR: floar or array
    @keyword power: power in the power law, default is given by goldreich 
                    & Scoville 1976, approximation gas kinetic temperature in 
                    optically thin medium, in the inner CSE
                    
                    (default: 0.5)
    @type power: float or array
    
    @return: radius at temperature T according to the power law, in the same 
             units as R_STAR
    @rtype: float or array
    
    """
    
    return (float(T_STAR)/float(T))**(1/float(power))*float(R_STAR)



def makeStars(models,star_name,id_type,path,code,\
              path_combocode=os.path.join(os.path.expanduser('~'),\
                                          'ComboCode')):
    
    '''
    Make a list of dummy Star() objects.

    @param models: model_ids for the new stars
    @type models: list[string]
    @param star_name: The star name from Star.dat
    @type star_name: string
    @param id_type: The type of id (PACS, GASTRONOOM, MCMAX)
    @type id_type: string
    @param path: Output folder in the code's home folder
    @type path: string
    @param code: The code (which is not necessarily equal to id_type, such as 
                 for id_type == PACS)
    @type code: string
    @param path_combocode: CC home folder
                           
                           (default: '~/ComboCode/')
    @type path_combocode: string
    
    @return: The parameter sets, mostly still empty!
    @rtype: list[Star()]
    
    '''
    
    extra_pars = dict([('path_'+code.lower(),path)])
    star_grid = [Star(example_star={'STAR_NAME':star_name,\
                                    'LAST_%s_MODEL'%id_type.upper():model},\
                      path_combocode=path_combocode,**extra_pars) 
                 for model in models]
    return star_grid
      

    
class Star(dict):
    
    """
    Star class maintains information about a stellar model and its properties.

    Inherits from dict.
    
    """



    def __init__(self,path_gastronoom=None,path_mcmax=None,extra_input=None,\
                 path_combocode=os.path.join(os.path.expanduser('~'),\
                                             'ComboCode'),
                 example_star=dict()):
        
        """
        Initiate an instance of the STAR class.
        
        @keyword path_gastronoom: path in ~/GASTRoNOoM/ for modeling out/input
                                  
                                  (default: None)
        @type path_gastronoom: string
        @keyword path_mcmax: the folder in ~/MCMax/ for modeling out/input
        
                             (default: None)
        @type path_mcmax: string
        @keyword path_combocode: full path to ComboCode
        
                                 (default: '/home/robinl/ComboCode')
        @type path_combocode: string
        @keyword example_star: if not None the STAR object is exact duplicate 
                               of example_star. Can be a normal dictionary as 
                               well. Paths are not copied and need to be given 
                               explicitly.
                                    
                               (default: None)
        @type example_star: dict or Star()                                  
        @keyword extra_input: extra input that you wish to add to the dict
        
                              (default: None)
        @type extra_input: dict or Star()
        
        @return: STAR object in the shape of a dictionary which includes all 
                 stellar data available, if None are passed for both options it
                 is an empty dictionary; if an example star is passed it has a 
                 dict that is an exact duplicate of the example star's dict
        @rtype: Star()
        
        """    
            
        super(Star, self).__init__(example_star)
        if extra_input <> None: self.update(extra_input)
        self.r_solar = 6.955e10         #in cm
        self.m_solar = 1.98892e33      #in g
        self.year = 31557600.            #julian year in seconds
        self.au = 149598.0e8             #in cm
        self.c = 2.99792458e10          #in cm/s
        self.h = 6.62606957e-27         #in erg*s Planck constant
        self.k = 1.3806488e-16          #in erg/K Boltzmann constant
        self.pc = 3.08568025e16         #in cm

        self.path_combocode = path_combocode
        dust_path = os.path.join(self.path_combocode,'Data')
        self.species_list = DataIO.getInputData(path=dust_path,\
                                         keyword='SPECIES_SHORT',\
                                         filename='Dust.dat')
        self.path_gastronoom = path_gastronoom        
        self.path_mcmax = path_mcmax
        self.convertRadialUnit()
        


    def __getitem__(self,key):

        """
        Overriding the standard dictionary __getitem__ method.
        
        @param key: Star()[key] where key is a string for which a corresponding
                    dictionary value is searched. If the key is not present in 
                    the dictionary, an attempt is made to calculate it from 
                    already present data; if it fails a KeyError is still 
                    raised. 
        @type key: string            
        
        @return: The value from the Star() dict for key
        @rtype: any
        
        """
        
        if not self.has_key(key):
            self.missingInput(key)
            return super(Star,self).__getitem__(key)
        elif super(Star,self).__getitem__(key) == '%':
            del self[key]
            self.missingInput(key)
            value = super(Star,self).__getitem__(key)
            self[key] = '%'
            return value 
        else:
            return super(Star,self).__getitem__(key)



    def __cmp__(self,star):
        
        """
        Overriding the standard dictionary __cmp__ method.
        
        A parameter set (dictionary of any type) is compared with this instance
        of Star(). 
        
        An attempt is made to create keys with values in each dict, if the 
        other has keys that are not present in the first. If this fails, False
        is returned.     
        
        @param star: A different parameter set. 
        @type star: dict or Star()             
        
        @return: The comparison between this object and star
        @rtype: bool
        
        """
        
        try:
            all_keys = set(self.keys() + star.keys())
            for k in all_keys:
                if not self.has_key(): 
                    self[k]
                if not star.has_key():
                    star[k]
            #if len(self) > len(star):
                #changed_keys = [star[k] 
                                #for k in self.keys() 
                                #if not star.has_key(k)]
                #print "Initialized keys in STAR2 from STAR1 == STAR2 comparison : \n" + str(changed_keys)
            #if len(self) < len(star):
                #changed_keys = [self[k] for k in star.keys() if not self.has_key(k)]
                #print "Initialized keys in STAR1 from STAR1 == STAR2 comparison : \n" + str(changed_keys)
        except KeyError:
            print 'Comparison error: Either STAR1 or STAR2 contains a key ' + \
                  'that cannot be initialized for the other.'
            print 'Both STAR instances are considered to be unequal.'
        finally:
            if isinstance(star, super(Star)):
                return cmp(super(Star,self), super(Star,star))
            else:
                return cmp(super(Star,self), star)                 

                      
                            
    def addCoolingPars(self):
        
        '''
        Add Star parameters from the cooling database. 
        
        Any existing parameters are overwritten!
        
        '''
        
        cooling_path = os.path.join(os.path.expanduser('~'),'GASTRoNOoM',\
                                    self.path_gastronoom,\
                                    'GASTRoNOoM_cooling_models.db')
        cool_db = Database.Database(cooling_path)
        cooling_dict = cool_db[self['LAST_GASTRONOOM_MODEL']].copy()
        cooling_keys = ['T_STAR','R_STAR','TEMDUST_FILENAME','MDOT_GAS']
        for k in cooling_dict.keys():
            if k not in cooling_keys: del cooling_dict[k]            
        cooling_dict['R_STAR'] = float(cooling_dict['R_STAR'])/self.r_solar
        self.update(cooling_dict)



    def writeDensity(self):
        
        '''
        Write full density (vs stellar radii) profile for a star.
        
        Only if MCMax model_id is available! 
        
        '''
        
        if not self['LAST_MCMAX_MODEL']: return
        dens = self.getMCMaxOutput(int(self['NTHETA'])*int(self['NRAD']),\
                                   keyword='DENSITY')
        rad = array(self.getMCMaxOutput(int(self['NRAD'])))\
                /self.r_solar/self['R_STAR']
        dens = Data.reduceArray(dens,self['NTHETA'])
        DataIO.writeCols(os.path.join(os.path.expanduser('~'),'MCMax',\
                                      self.path_mcmax,'models',\
                                      self['LAST_MCMAX_MODEL'],\
                                      'density_profile_%s.dat'%\
                                      self['LAST_MCMAX_MODEL']),[rad,dens])
        


    def readKappas(self):
        
        '''
        Read the kappas.dat file of an MCMax model.
    
        '''
        
        opas = DataIO.readCols(os.path.join(os.path.expanduser('~'),'MCMax',\
                                            self.path_mcmax,'models',\
                                            self['LAST_MCMAX_MODEL'],\
                                            'kappas.dat'))
        return opas.pop(0),opas
                            


    def convertRadialUnit(self):
        
        '''
        Convert any radial unit for shell parameters to R_STAR.
        
        '''
        
        if self['R_SHELL_UNIT'] != 'R_STAR':
            shell_units = ['CM','M','KM','AU']
            unit_index = shell_units.index(self['R_SHELL_UNIT'].upper())
            unit_conversion = [1./(self.r_solar*self['R_STAR']),\
                               10.**2/(self.r_solar*self['R_STAR']),\
                               10.**5/(self.r_solar*self['R_STAR']),\
                               self.au/(self.r_solar*self['R_STAR'])]
            for par in ['R_INNER_GAS','R_INNER_DUST','R_OUTER_GAS',\
                        'R_OUTER_DUST'] \
                    + ['R_MAX_' + species for species in self.species_list] \
                    + ['R_MIN_' + species for species in self.species_list]:
                if self.has_key(par):
                    self[par] = self[par]*unit_conversion[unit_index]
        else:
            pass
                            


    def getMCMaxOutput(self,incr,keyword='RADIUS',filename='denstemp.dat',\
                       single=1):
        
        """
        Search MCMax output for relevant structural information.
    
        @param incr: length of partial list that is needed from MCMax output
        @type incr: int
        
        @keyword keyword: the type of information required, always equal to one
                          of the keywords present in the outputfiles of MCMax
                          
                          (default: 'RADIUS')
        @type keyword: string
        @keyword filename: name of the file searched, keyword has to be present
                           in it
                           
                           (default: 'denstemp.dat')
        @type filename: string
        @keyword single: return a list of only the first element on every row
        
                         (default: 1)
        @type single: bool
        
        @return: The requested data from MCMax output
        @rtype: list[]
        
        """
        
        data = DataIO.readFile(os.path.join(os.path.expanduser('~'),'MCMax',\
                               self.path_mcmax,'models',\
                               self['LAST_MCMAX_MODEL'],filename),' ')
        i = 1
        while ' '.join(data[i-1]).upper().find(keyword) == -1:
            i += 1
        if not incr:
            i -= 1
            incr = 1
        if single:
            return [float(line[0]) for line in data[i:i+int(incr)]]
        else:
            return [line for line in data[i:i+int(incr)]]
            

    
    def removeMutableMCMax(self,mutable,var_pars):
        
        """
        Remove mutable parameters after an MCMax run.
    
        @param mutable: mutable keywords
        @type mutable: list[string]
        @param var_pars: parameters that are varied during gridding, these will
                         not be removed and are kept constant throughout the 
                         iteration
        @type var_pars: list[string]
        
        """
        
        #- remove keys which should be changed by output of new mcmax model, 
        #- but only the mutable input!!! 
        for key in self.keys():
            if key in mutable \
                       + ['R_MAX_' + species for species in self['DUST_LIST']]\
                       + ['T_DES_' + species for species in self['DUST_LIST']]\
                       + ['R_DES_' + species for species in self['DUST_LIST']]\
                    and key not in var_pars:
                del self[key]
        
        #- Check the effective destruction temperature of every species, and 
        #- see if max and min T's are as requested.
        self.checkT()
        
        #- No point in keeping zeroes around for T_DES or T_MIN
        for species in self['DUST_LIST']:
            for par in ('T_DES_' + species, 'T_MIN_' + species):
                if self.has_key(par):
                    if not float(self[par]):
                        del self[par]
                    
  

    def removeMutableGastronoom(self,mutable,var_pars):
        
        """
        Remove mutable parameters after a GASTRoNOoM run.
    
        @param mutable: mutable parameters
        @type mutable: list[string]
        @param var_pars: parameters that are varied during gridding, these will
                         not be removed and are kept constant throughout the 
                         iteration
        @type var_pars: list[string]
        
        """
        
        for key in self.keys():
            if key in mutable and key not in var_pars:
                del self[key]
                    
 
    
    def updateMolecules(self,parlist):
        
        '''
        Update variable information in the molecule instances of this star.
        
        @param parlist: parameters that have to be updated.
        @type parlist: list[string]
        
        '''
        
        for molec in self['GAS_LIST']:
            molec.updateParameters(pardict=dict([(k,self[k]) 
                                                 for k in parlist]))
    


    def addLineList(self):
        
        """ 
        Take molecular transitions from a line list and wavelength range.
        
        Based on the GASTRoNOoM radiat and indices data files. See Molecule.py
        for more info.
        
        """
        
        try:
            gas_list = list(self['GAS_LINES'])
        except KeyError:
            gas_list = []
        for molec in self['GAS_LIST']:
            radiat = molec.radiat
            wave = radiat.getFrequency(unit=self['LL_UNIT'])
            low = radiat.getLowerStates()
            up = radiat.getUpperStates()
            if type(self['LL_TELESCOPE']) is not types.ListType:
                self['LL_TELESCOPE'] = [self['LL_TELESCOPE']]
            for telescope in self['LL_TELESCOPE']:
                if telescope == 'PACS-H2O' and not molec.isWater():
                    telescope = 'PACS'
                elif telescope == 'PACS' and molec.isWater():
                    telescope = 'PACS-H2O'
                if not molec.spec_indices:
                    #- molec.ny_low is the number of levels in gs vib state
                    #- molec.ny_up is the number of levels above gs vib state
                    #- generally ny_up/ny_low +1 is the number of vib states
                    ny_low = molec.ny_low
                    n_vib = int(molec.ny_up/ny_low) + 1 
                    indices = [[i+1,int(i/ny_low),i-ny_low*int(i/ny_low)]
                               for i in xrange(molec.ny_low*n_vib)]
                    new_lines = [Transition.Transition(\
                                    molecule=molec,telescope=telescope,\
                                    vup=int(indices[u-1][1]),\
                                    jup=int(indices[u-1][2]),\
                                    vlow=int(indices[l-1][1]),\
                                    jlow=int(indices[l-1][2]),\
                                    offset=self['LL_OFFSET'],\
                                    n_quad=self['N_QUAD'],\
                                    use_maser_in_sphinx=\
                                                  self['USE_MASER_IN_SPHINX'],\
                                    path_combocode=self.path_combocode,\
                                    path_gastronoom=self.path_gastronoom)
                                 for l,u,w in zip(low,up,wave)
                                 if w > self['LL_MIN'] and w < self['LL_MAX']]
                else:
                    indices = molec.radiat_indices
                    quantum = ['v','j','ka','kc']
                    new_lines = [] 
                    for l,u,w in zip(low,up,wave):
                        if w > self['LL_MIN'] and w < self['LL_MAX']:
                            quantum_dict = dict()
                            #- some molecs only have 2 or 3 quantum numbers
                            for i in xrange(1,len(indices[0])):    
                                quantum_dict[quantum[i-1]+'up'] = \
                                                        int(indices[u-1][i])
                                quantum_dict[quantum[i-1]+'low'] = \
                                                        int(indices[l-1][i])
                            new_lines.append(Transition.Transition(\
                                        molecule=molec,\
                                        telescope=telescope,\
                                        offset=self['LL_OFFSET'],\
                                        n_quad=self['N_QUAD'],\
                                        path_combocode=self.path_combocode,\
                                        use_maser_in_sphinx=\
                                                  self['USE_MASER_IN_SPHINX'],\
                                        path_gastronoom=self.path_gastronoom,\
                                        **quantum_dict)) 
            gas_list.extend(new_lines)
        self['GAS_LINES'] = tuple(set(gas_list))



    def calcN_QUAD(self):
        
        """
        Set the default value of N_QUAD to 100. 
        
        Only used when auto selecting transition based on a wavelength range.
        
        """
        
        if not self.has_key('N_QUAD'):
            self['N_QUAD'] = 100
        else:
            pass
    
    
    
    def calcLL_OFFSET(self):
        
        """
        Set the default value of LL_OFFSET to 0.0. 
        
        Only used when auto selecting transitions based on a wavelength range.
        
        """
        
        if not self.has_key('LL_OFFSET'):
            self['LL_OFFSET'] = 0.0
        else:
            pass
    
        

    def checkT(self):
        
        """
        Search input list for minimum temperature.
    
        Method prints the actual minimum T for which the model was calculated.
        
        Note that the density drops to zero gradually and that the criterium
        has to be sudden change of slope. Check criterium if the printed T is 
        not good enough as determination of max radius IS correct.
        
        """
        
        coldens = ColumnDensity.ColumnDensity(self)
        for index,species in enumerate(self['DUST_LIST']):
            self['T_DES_%s'%species] = coldens.t_des[species]
            self['R_DES_%s'%species] = coldens.r_des[species]\
                                        /self.r_solar/self['R_STAR']
            print 'The EFFECTIVE maximum temperature for species %s '%species+\
                  'is %.2f K, at radius %.2f R_STAR.'\
                  %(self['T_DES_%s'%species],self['R_DES_%s'%species])
            
        species_list_min = [species 
                            for species in self.species_list 
                            if self.has_key('T_MIN_%s'%species) \
                                or self.has_key('R_MAX_%s'%species)]
        for species in species_list_min:
            print 'The EFFECTIVE minimum temperature for species'+\
                  ' %s is %.2f K at maximum radius %.2f R_STAR.'\
                  %(species,coldens.t_min[species],\
                    coldens.r_max[species]/self.r_solar/self['R_STAR'])
            if self.has_key('T_MIN_%s'%species):
                print 'The REQUESTED minimum temperature for species '+\
                      '%s is %.2f K.'%(species,self['T_MIN_%s'%species])
            if self.has_key('R_MAX_%s'%species):
                print 'The REQUESTED maximum radius for species'+\
                      '%s is %.2f R_STAR.'%(species,self['R_MAX_%s'%species])
            print 'The EFFECTIVE outer radius of the shell is %.2f R_STAR.'\
                  %(coldens.r_outer/self.r_solar/self['R_STAR'])
            print 'Note that if R_MAX is ~ the effective outer radius, the ' +\
                  'requested minimum temperature may not be reached.'
        return
    

    
    def getFullNameMolecule(self,short_name):
        
        '''
        Get the full name of a molecule, based on it's short name, 
        if it is present in the GAS_LIST.
                
        @return: Name the name. None if not available.
        @rtype: string
        
        '''
        
        molecule = [molec.molecule_full 
                    for molec in self['GAS_LIST'] 
                    if molec.molecule == short_name]
        if not molecule:
            return None
        #- Return first only, if multiple there's multiple requested molecules 
        #- of the same type (fi different abundance)
        else:
            return molecule[0]     



    def getShortNameMolecule(self,full_name):
        
        '''
        Get the short name of a molecule, based on it's full name, 
        if it is present in the GAS_LIST.
        
        @param full_name: The full name of a molecule from Molecule.dat
        @type full_name: string
        
        @return: None if not available, otherwise the short hand name.
        @rtype: string
        
        '''
        
        molecule = [molec.molecule 
                    for molec in self['GAS_LIST'] 
                    if molec.molecule_full == full_name]
        if not molecule:
            return None
        #- Return first only, if multiple there's multiple requested molecules 
        #- of the same type (fi different abundance)
        else:
            return molecule[0]     
      

     
    def getMolecule(self,molec_name):
        
        '''
        Get a Molecule() object based on the molecule name. 
        
        A Star() object always has only one version of one molecule.
        
        @param molec_name: short name of the molecule
        @type molec_name: string
        
        @return: The molecule
        @rtype: Molecule()
        
        '''
        
        try:
            return [molec 
                    for molec in self['GAS_LIST'] 
                    if molec.molecule == molec_name][0]
        except IndexError:
            return None
    
    
    
    def getTransition(self,sample):
        
        '''
        Return a Transition() object that has the same parameters as sample. 
        
        The actual model ids are not included in this comparison! 
        
        None is returned if no match is found. 
        
        @param sample: A sample transition to be cross referenced with the 
                       transitions in this Star() object. If a match is found, 
                       it is returned.
        @type sample: Transition()
        @return: If a match is found, this transition is returned.
        @rtype: Transition()
        
        '''
         
        i = 0
        while i < len(self['GAS_LINES']) and sample != self['GAS_LINES'][i]:
            i += 1
        if i == len(self['GAS_LINES']):
            return None
        else:
            return self['GAS_LINES'][i]
        
    
     
    def getTransList(self):
        
        '''
        Return a list of (transmodelid,molecmodelid,dictionary) 
        for every transition in the Star model.
        
        '''
        
        return [(trans.getModelId(),trans.molecule.getModelId(),\
                 trans.makeDict())
                for trans in self['GAS_LINES']]



    def getTransitions(self,molec):
        
        '''
        Return a list of all transitions associated with a single molecule.
        
        @param molec: the shorthand notation of the molecule
        @type molec: string
        
        @return: All transitions for this molecule
        @rtype: list[Transition()]
        
        '''
        
        return [trans 
                for trans in self['GAS_LINES'] 
                if trans.molecule.molecule==molec]



    def getDustTemperature(self):
         
        '''
        Return the dust temperature profile from the file made for GASTRoNOoM.
        
        This is the total dust temperature without separate components for the 
        different dust species.
        
        @return: Two lists including the radial grid (in cm) and the
                 temperature (K) as well as a key.
        @rtype: (list,list,string)
        
        '''
        
        try:
            data = DataIO.readCols(self['DUST_TEMPERATURE_FILENAME'])
            rad = data[0]*self.r_solar*self['R_STAR']
            temp = data[1]
        except IOError:
            rad = []
            temp = []
        key = '$T_{\mathrm{d, avg}}$'
                #self['LAST_MCMAX_MODEL'].replace('_','\_')
        return rad, temp, key
        
         
         
    def getDustTemperaturePowerLaw(self,power):
        
        '''
        Return a dust temperature power law of the form as suggested by 
        observational evidence. 
        
        See Thesis p32, where power is p in 
        T(r) = T_eff*(2*r/R_STAR)**(-p)
        
        @param power: The power in the power law T(r) given above.
        @type power: float
        @return: Two lists including the radial grid (in cm) and the temperature
                    (K) as well as a key.
        @rtype: (list,list,string)
        
        '''
        
        power = float(power)
        try:
            rad = array(self.getMCMaxOutput(incr=int(self['NRAD'])))
            temp = self['T_STAR']*(2*rad/self.r_solar/self['R_STAR'])**(-power)
        except IOError:
            rad = []
            temp = []
        #key = '$T_\mathrm{d} = %i\ K*(2r/R_*)^{-%.1f}$'\
        #        %(power,int(self['T_STAR']))
        #key = 'Power law ($p = %.2f$) for $T_\mathrm{eff} = %i\ K$'\
        #        %(power,int(self['T_STAR']))
        key = 'Eq.~2 with $s=1$'
        return rad, temp, key
    
    
    
    def getDustTemperatureSpecies(self):
         
        ''' 
        Return the temperature profiles of all species included in Star object.
        
        This information is taken from the denstempP## files for each species.
        
        @return: Three lists: one for all radial grids (lists in cm) of the 
                    species, one for all temperature profiles (lists in K) and 
                    one for all keys (strings)
        @rtype: (list(lists),list(lists),list(strings))
        
        '''
        
        radii = [array(self.getMCMaxOutput(incr=int(self['NRAD']),\
                                          filename='denstempP%.2i.dat'%(i+1)))
                 for i in xrange(len(self['DUST_LIST']))]
        temps = [self.getMCMaxOutput(incr=int(self['NRAD'])\
                                            *int(self['NTHETA']),\
                                     keyword='TEMPERATURE',\
                                     filename='denstempP%.2i.dat'%(i+1))
                 for i in xrange(len(self['DUST_LIST']))]      
        temps = [Data.reduceArray(t,self['NTHETA'])
                    for t in temps]
        radii = [r[t<=self['T_DES_%s'%sp]] 
                 for r,t,sp in zip(radii,temps,self['DUST_LIST'])]
        temps = [t[t<=self['T_DES_%s'%sp]] 
                 for t,sp in zip(temps,self['DUST_LIST'])]
        plot_names = DataIO.getInputData(path=os.path.join(self.path_combocode,\
                                                    'Data'),\
                                  keyword='SPECIES_PLOT_NAME',\
                                  filename='Dust.dat')
        keys = [plot_names[self.species_list.index(d)]  
                for d in self['DUST_LIST']]
        return radii,temps,keys

    
    
    def getGasVelocity(self):
        
        '''
        Give the velocity profile of the gas read from a GASTRoNOoM model.
        
        @return: The radius (in cm) and velocity (in cm/s) profile
        @rtype: (array,array)
        
        '''
                
        fgr_file = os.path.join(os.path.expanduser('~'),'GASTRoNOoM',\
                                self.path_gastronoom,'models',\
                                self['LAST_GASTRONOOM_MODEL'],\
                                'coolfgr_all%s.dat'\
                                %self['LAST_GASTRONOOM_MODEL'])
        rad = DataIO.getGastronoomOutput(filename=fgr_file,keyword='RADIUS',\
                                         return_array=1)
        vel = DataIO.getGastronoomOutput(filename=fgr_file,keyword='VEL',\
                                         return_array=1)
        return (rad,vel)
        
        

    def calcTLR(self):  
        
        """
        Stefan-Boltzmann's law.
            
        Star() object needs to have at least 2 out of 3 parameters (T,L,R), 
        with in L and R in solar values and T in K.
    
        The one missing parameter is calculated. 
    
        This method does nothing if all three are present.
        
        """
        
        Tsun = 5778.0
        Lsun = 3.839e33
        Rsun = 6.96e10
        if not self.has_key('T_STAR'):
            self['T_STAR']=(float(self['L_STAR'])/float(self['R_STAR'])**2.)\
                                **(1/4.)*Tsun
        elif not self.has_key('L_STAR'):
            self['L_STAR']=(float(self['R_STAR']))**2.*\
                                (float(self['T_STAR'])/Tsun)**4.
        elif not self.has_key('R_STAR'):
            self['R_STAR']=(float(self['L_STAR'])*\
                                (Tsun/float(self['T_STAR']))**4)**(1/2.)
        else:
            pass 



    def getClassAttr(self,missing_key):
        
        """
        Fill in Class attributes specific for a star. All these parameters are
        taken from Star.dat.
    
        @param missing_key: The missing key, taken from Star.dat
        @type missing_key: string
        
        
        """
        
        if not self.has_key(missing_key):
            self[missing_key] \
                = DataIO.getInputData(path=os.path.join(self.path_combocode,'Data'),\
                               keyword=missing_key,\
                               remove_underscore=missing_key == \
                                                    'STAR_NAME_PLOTS')\
                              [self['STAR_INDEX']]
        else:
            pass
 


    def calcLL_GAS_LIST(self):
        
        '''
        Define Molecule() objects for the molecules requested in the LineList
        mode.
        
        '''
        
        if not self.has_key('LL_GAS_LIST'):
            if type(self['LL_MOLECULES']) is types.ListType \
                    or type(self['LL_MOLECULES']) is types.TupleType:
                self['LL_GAS_LIST'] = [Molecule.Molecule(molecule=molec,
                                            linelist=1,\
                                            path_combocode=self.path_combocode) 
                                       for molec in self['LL_MOLECULES']]
            else:
                self['LL_GAS_LIST'] = [Molecule.Molecule(linelist=1,\
                                            molecule=self['LL_MOLECULES'],\
                                            path_combocode=self.path_combocode)]
        else:
            pass
        
   
    
    def calcUSE_MASER_IN_SPHINX(self):
        
        '''
        Set the default value of USE_MASER_IN_SPHINX parameter.
        
        '''
        
        if not self.has_key('USE_MASER_IN_SPHINX'):
            self['USE_MASER_IN_SPHINX']=0
        else:
            pass


    
    def calcLOGG(self):
        
        """
        Set the default value of LOGG to 0.
        
        """
        
        if not self.has_key('LOGG'):
            self['LOGG']=0
        else:
            pass

    

    def calcT_INNER_DUST(self):
        
        """
        Find the dust temperature at the inner radius in Kelvin.
        
        Taken from last mcmax model, and defined by the dust species able to 
        exist at the highest temperature; if no mcmax model is present, the 
        temperature is taken to be zero, indicating no inner radius T is 
        available.
        
        """        
        
        if not self.has_key('T_INNER_DUST'):
            try:
                rad = self.getMCMaxOutput(incr=int(self['NRAD']))
                temp_ori = self.getMCMaxOutput(incr=int(self['NRAD'])\
                                                    *int(self['NTHETA']),\
                                               keyword='TEMPERATURE')
                temp = Data.reduceArray(temp_ori,self['NTHETA'])
                rin = self['R_INNER_DUST']*self['R_STAR']*self.r_solar
                self['T_INNER_DUST'] = temp[argmin(abs(rad-rin))]
            except IOError:
                self['T_INNER_DUST'] = 0
        else:
            pass
        


    def calcTEMPERATURE_EPSILON_GAS(self):
        
        """
        If not present in input, TEMPERATURE_EPSILON_GAS is equal to 0.5.
        
        """
        
        if not self.has_key('TEMPERATURE_EPSILON_GAS'):
            self['TEMPERATURE_EPSILON_GAS'] = 0.5
        else:
            pass



    def calcTEMPERATURE_EPSILON2_GAS(self):
        
        """
        If not present in input, TEMPERATURE_EPSILON2_GAS is equal to 0, 
        in which case it will be ignored when making input file.
        
        """
        
        if not self.has_key('TEMPERATURE_EPSILON2_GAS'):
            self['TEMPERATURE_EPSILON2_GAS'] = 0
        else:
            pass



    def calcRADIUS_EPSILON2_GAS(self):
        
        """
        If not present in input, RADIUS_EPSILON2_GAS is equal to 0, \
        in which case it will be ignored when making input file.
        
        """
        
        if not self.has_key('RADIUS_EPSILON2_GAS'):
            self['RADIUS_EPSILON2_GAS'] = 0
        else:
            pass



    def calcTEMPERATURE_EPSILON3_GAS(self):
        
        """
        If not present in input, TEMPERATURE_EPSILON3_GAS is equal to 0, 
        in which case it will be ignored when making input file.
        
        """
        
        if not self.has_key('TEMPERATURE_EPSILON3_GAS'):
            self['TEMPERATURE_EPSILON3_GAS'] = 0
        else:
            pass



    def calcRADIUS_EPSILON3_GAS(self):
        
        """
        If not present in input, RADIUS_EPSILON3_GAS is equal to 0, 
        in which case it will be ignored when making input file.
        
        """
        
        if not self.has_key('RADIUS_EPSILON3_GAS'):
            self['RADIUS_EPSILON3_GAS'] = 0
        else:
            pass



    def calcDUST_TO_GAS_CHANGE_ML_SP(self):
        
        """
        Set default value of sphinx/mline specific d2g ratio to the 
        semi-empirical d2g ratio. In order to turn this off, set this
        parameter to 0 in the input file.
        
        """
        
        if not self.has_key('DUST_TO_GAS_CHANGE_ML_SP'):
            self['DUST_TO_GAS_CHANGE_ML_SP'] = self['DUST_TO_GAS']
        else:
            pass



    def calcR_INNER_GAS(self):
        
        """
        If not present in input, R_INNER_GAS is equal to R_INNER_DUST
    
        """
        
        if not self.has_key('R_INNER_GAS'):
            self['R_INNER_GAS'] = self['R_INNER_DUST']
        else:
            pass



    def calcUSE_DENSITY_NON_CONSISTENT(self):
        
        """
        Set USE_DENSITY_NON_CONSISTENT off by default.
        
        """
        
        if not self.has_key('USE_DENSITY_NON_CONSISTENT'):
            self['USE_DENSITY_NON_CONSISTENT'] = 0
        else:
            pass        



    def calcR_OUTER_DUST(self):
        
        """
        If not present in input, R_OUTER_DUST is calculated from 
        R_OUTER_DUST_AU.
            
        """
        
        if not self.has_key('R_OUTER_DUST'):
            if self.has_key('R_OUTER_DUST_AU'):
                self['R_OUTER_DUST'] = self['R_OUTER_DUST_AU']*self.au\
                                            /self['R_STAR']/self.r_solar
            elif self.has_key('R_OUTER_MULTIPLY'):
                self['R_OUTER_DUST'] = self['R_INNER_DUST']\
                                            *self['R_OUTER_MULTIPLY']
        else:
            pass
        


    def calcR_INNER_DUST(self):
    
        """
        Calculate the inner radius from MCMax output in stellar radii.
        
        If no MCMax model is calculated yet, R_{i,d} is the stellar radius.
        
        Else, the inner dust radius is taken where the density reaches a 
        threshold, defined by R_INNER_DUST_MODE:
        
            - MAX: Density reaches a maximum value, depends on the different 
                   condensation temperatures of the dust species taken into 
                   account 
            - ABSOLUTE: Density becomes larger than 10**(-51)
            - RELATIVE: Density becomes larger than 1% of maximum density
        
        Unless defined in the CC input file, the dust radius is updated every 
        time a new iteration starts.
        
        If no MCMax model is known, and destruction temperature iteration is 
        off, the inner radius is 2 stellar radii for calculation time reasons.
        
        """
    
        if not self.has_key('R_INNER_DUST'):
            if self.has_key('R_INNER_DUST_AU'):
                self['R_INNER_DUST'] = self['R_INNER_DUST_AU']*self.au\
                                                /self['R_STAR']/self.r_solar
            else:
                try:
                    dens_ori = array(self.getMCMaxOutput(\
                                                    incr=int(self['NRAD'])\
                                                        *int(self['NTHETA']),\
                                                    keyword='DENSITY'))
                    rad = array(self.getMCMaxOutput(incr=int(self['NRAD']),\
                                                    keyword='RADIUS'))
                    dens = Data.reduceArray(dens_ori,self['NTHETA'])
                    if self['R_INNER_DUST_MODE'] == 'MAX':
                        ri_cm = rad[argmax(dens)]
                    elif self['R_INNER_DUST_MODE'] == 'ABSOLUTE':
                        ri_cm = rad[dens>10**(-50)][0]
                    else:
                        ri_cm = rad[dens>0.01*max(dens)][0]
                    self['R_INNER_DUST'] = ri_cm/self.r_solar\
                                                /float(self['R_STAR'])
                except IOError:
                    self['R_INNER_DUST'] = 1.0
        else:
            pass



    def calcR_INNER_DUST_MODE(self):
         
        """
        The mode of calculating the inner radius from MCMax output, if present.
        
        Can be ABSOLUTE (dens>10**-50) or RELATIVE (dens[i]>dens[i+1]*0.01).
        
        CLASSIC reproduces the old method. 
        
        Set here to the default value of ABSOLUTE.
        
        """
        
        if not self.has_key('R_INNER_DUST_MODE'):
            self['R_INNER_DUST_MODE'] = 'ABSOLUTE'
        else:
            pass        



    def calcRID_TEST(self):
         
        """
        The mode of determining the dust temp profile. 
        
        Only for testing purposes.
        
            - Default is 'R_STAR', ie the temperature is taken from the stellar
              radius onward, regardless of what the inner radius is. 
        
            - 'R_INNER_GAS' is used for taking the dust temperature from the 
              inner gas radius onward. 
        
            - 'BUGGED_CASE' is the old version where r [R*] > R_STAR [R_SOLAR]. 
        
        """
        
        if not self.has_key('RID_TEST'):
            self['RID_TEST'] = 'R_STAR'
        else:
            pass 



    def calcSTAR_NAME(self):
        
        """
        Checking if STAR_NAME is present. 
        
        If not, the star_name is arbitrary and equal to 'model'.
    
        """
        if not self.has_key('STAR_NAME'):
            self['STAR_NAME'] = 'model'
        else:
            pass



    def calcSTAR_INDEX(self):
        
        """
        Finding the star's database index from STAR_NAME if keyword is present.
        
        This index is the position of the star in Star.dat.
        
        """
        
        try:
            self['STAR_INDEX'] = DataIO.getInputData(path=os.path.join(\
                                                        self.path_combocode,\
                                                        'Data'))\
                                             .index(self['STAR_NAME'])
        except KeyError,ValueError: 
            self['STAR_INDEX'] = -1
            self['DATA_MOL'] = 0
            print 'No (correct) star name has been supplied. ' +\
                  'Calculation continues without data.'

    

    def calcDATA_MOL(self):
        
        '''
        Set default value of DATA MOL to 0.
        
        '''
        
        if not self.has_key('DATA_MOL'):
            self['DATA_MOL'] = 0
        else:
            pass
        


    def calcPATH_GAS_DATA(self):
        
        """
        If not present, the path is taken to be a default.
        
        Currently data can be read from /home/elvired/allspectra/
    
        """
        
        if not self.has_key('PATH_GAS_DATA'):
            self['PATH_GAS_DATA'] = '/home/elvired/allspectra/'
        else:
            pass
        


    def calcSPEC_DENS_DUST(self):
        
        """
        Calculating average specific density of dust shell.
        
        This is based on the input dust species abundances and their specific 
        densities.
    
        """
    
        if not self.has_key('SPEC_DENS_DUST'):
            self['SPEC_DENS_DUST'] = sum([float(self['A_' + species])*spec_dens
                                          for species in self['DUST_LIST']
                                          for species_short,spec_dens in zip(\
                                            self.species_list,\
                                            DataIO.getInputData(path=os.path.join(\
                                                  self.path_combocode,'Data'),\
                                                         keyword='SPEC_DENS',\
                                                         filename='Dust.dat'))
                                          if species == species_short])
        else:
            pass
            


    def calcLAST_MCMAX_MODEL(self):
        
        """
        Creates empty string if not present yet.
    
        """
        
        if not self.has_key('LAST_MCMAX_MODEL'):
            self['LAST_MCMAX_MODEL'] = ''
        else:
            pass
        


    def calcLAST_PACS_MODEL(self):
        
        """
        Creates empty string if not present yet.
    
        """
        
        if not self.has_key('LAST_PACS_MODEL'):
            self['LAST_PACS_MODEL'] = ''
        else:
            pass
        


    def calcLAST_GASTRONOOM_MODEL(self):
        
        """
        Creates empty string if not present yet.
    
        """
        
        if not self.has_key('LAST_GASTRONOOM_MODEL'):
            self['LAST_GASTRONOOM_MODEL'] = ''
        else:
            pass
    

    
    def calcDRIFT(self):
        
        """
        Find terminal drift velocity from last calculated GASTRoNOoM model.
        
        Units are km/s and is given for grain size 0.25 micron.
        
        If no GASTRoNOoM model exists, the drift is taken to be 0.
        
        """
        
        if not self.has_key('DRIFT'):
            try:
                #- The last 10 entries should be roughly constant anyway, 
                #- ~terminal values
                self['DRIFT'] = self.getAverageDrift()[-5]/10.**5    
            except IOError:
                self['DRIFT'] = 0
                print 'No GASTRoNOoM model has been calculated yet, drift ' + \
                      'is unknown and set to the default of 0.'
        else:
            pass
        


    def calcM_DUST(self):
        
        """
        Find total dust mass, based on sigma_0 in the case of a power law.
    
        """
        
        if not self.has_key('M_DUST'):
            if self['DENSTYPE'] == 'POW':
                if self['DENSPOW'] == 2:
                    self['M_DUST']  \
                        = 2*pi*self['DENSSIGMA_0']\
                        *(self['R_INNER_DUST']*self['R_STAR']*self.r_solar)**2\
                        *log(self['R_OUTER_DUST']/float(self['R_INNER_DUST']))\
                        /self.m_solar
                else:
                    self['M_DUST'] \
                        = 2*pi*self['DENSSIGMA_0']\
                        *(self['R_INNER_DUST']*self['R_STAR']*self.r_solar)**2\
                        /(2.-self['DENSPOW'])/self.m_solar\
                        *((self['R_OUTER_DUST']/float(self['R_INNER_DUST']))\
                        **(2.-self['DENSPOW'])-1.)
            else:
                pass
        else:
            pass
        


    def calcMDOT_MODE(self):
        
        '''
        Set the default value of MDOT_MODE to constant.
        
        '''
        
        if not self.has_key('MDOT_MODE'):
            self['MDOT_MODE'] = 'CONSTANT'
        else:
            pass



    def calcMDOT_GAS_START(self):
        
        '''
        Set the default value of MDOT_GAS_START equal to MDOT_GAS.
        
        '''
        
        if not self.has_key('MDOT_GAS_START'):
            self['MDOT_GAS_START'] = self['MDOT_GAS']
        else:
            pass
        


    def calcV_EXP_DUST(self):
        
        """
        Calculate dust terminal velocity from gas terminal velocity and drift.
        
        Given in km/s.
        
        """

        if not self.has_key('V_EXP_DUST'):
            self['V_EXP_DUST']= float(self['VEL_INFINITY_GAS']) \
                                    + float(self['DRIFT'])
        else:
            pass    



    def calcRT_SED(self):
        
        '''
        Set the default value of MCMax ray-tracing of the SED to False.
        
        '''
        
        if not self.has_key('RT_SED'):
            self['RT_SED']= 0
        else:
            pass         



    def calcIMAGE(self):
        
        '''
        Set the default value of MCMax image to False.
        
        '''
        
        if not self.has_key('IMAGE'):
            self['IMAGE']= 0
        else:
            pass    



    def calcREDO_OBS(self):
        
        '''
        Set the default value of redoing observation files to False.
        
        '''
        
        if not self.has_key('REDO_OBS'):
            self['REDO_OBS']= 0
        else:
            pass    
        
 
    
    def calcR_MAX(self,missing_key):
        
        """
        Calculate the maximum existence radii for dust species.
        
        Based on T_MIN_SPECIES for the species, and derived from mcmax output.
        
        If not MCMax model available, a power law is assumed. If T_MIN is not 
        given, no boundaries are assumed. 
        
        Is given in solar radii.
        
        @param missing_key: the missing max radius for a species that is needed
                            Of the format R_MAX_SPECIES.
        @type missing_key: string
        
        """
        
        if not self.has_key(missing_key):
            #- R_MAX is for T_MIN
            try: 
                temp = float(self[missing_key.replace('R_MAX','T_MIN',1)])
                try:
                    #- if T_CONTACT: no specific species denstemp files, 
                    #- so denstemp.dat is taken
                    inputname = float(self['T_CONTACT']) \
                                    and 'denstemp.dat' \
                                    or 'denstempP%.2i.dat' \
                                       %self['DUST_LIST'].index(missing_key[6:])
                    
                    rad_list = self.getMCMaxOutput(int(self['NRAD']),\
                                                   keyword='RADIUS',\
                                                   filename=inputname)
                    temp_list = self.getMCMaxOutput(int(self['NRAD'])\
                                                        *int(self['NTHETA']),\
                                                    keyword='TEMPERATURE',\
                                                    filename=inputname)
                    temp_list = Data.reduceArray(temp_list,self['NTHETA'])
                    
                    i = 0
                    #- if tmin is larger than temp_list[0], indexerror raises, 
                    #- and vice versa: no dust
                    #- if tmin is smaller than temp_list[len], indexerror 
                    #- raises, and vice versa: all dust
                    try:
                        while temp_list[i] < temp or temp_list[i+1] > temp:
                            i += 1
                        rad = Interpol.linInterpol([temp_list[i],\
                                                    temp_list[i+1]],\
                                                   [rad_list[i],\
                                                    rad_list[i+1]],\
                                                   temp)\
                                                 /(self.r_solar*self['R_STAR'])
                    except IndexError:

                        #- if T_MIN (for R_MAX) > temp_list[0] then no dust can
                        #- be present of the species
                        #- for TMIN RMAX should be made very small, ie R*
                        if temp > temp_list[0]:
                            rad = self['R_STAR']

                        #- on the other hand, if TMIN < temp_list[len-1]
                        #- all dust is allowed, so raise KeyError, such that no
                        #- R_MAX is entered in STAR
                        elif temp < temp_list[-1]:
                            raise KeyError
                        
                        else:
                            print 'Something went wrong when searching for ' +\
                                  'R_MAX corresponding to T_MIN... Debug!'    
                    self[missing_key] = rad
                
                except IOError:
                    self[missing_key] = powerRfromT(float(temp),\
                                                    float(self['T_STAR']),\
                                                    power=float(self\
                                                            ['POWER_T_DUST']))\
                                                   /2.
            except KeyError:
                self[missing_key] = ''
        else:
            pass        


                            
    def calcT_DES(self,species):
        
        """
        Find the max temperature at which a dust species can exist.
        
        First, the CC inputfile is searched for T_MAX_SPECIES, in which case
        the sublimation temperature is constant. T_MAX is never made by Star()!
        
        If not present, Dust.dat info is taken, being either a sublimation 
        temperature, or the coefficients to calculate a pressure dependent
        sublimation temperature. These are set using T_DESA_ and T_DESB_SPECIES
        
        This assumes TDESITER to be on.
        
        @param species: The dust species
        @type species: string
        
        """
        
        if not self.has_key('T_DESA_' + species) \
                or not self.has_key('T_DESB_' + species):
            try:
                if not self['T_MAX_' + species]:
                    del self['T_MAX_' + species]
                self['T_DESA_' + species] = 10.0**(4)/self['T_MAX_' + species]
                self['T_DESB_' + species] = 10.0**(-4)
            except KeyError:
                species_index = self.species_list.index(species)
                species_tdesa = DataIO.getInputData(path=os.path.join(\
                                                  self.path_combocode,'Data'),\
                                             keyword='T_DESA',\
                                             filename='Dust.dat')\
                                            [species_index]
                if species_tdesa:
                    self['T_DESA_' + species] = 10.0**(4)\
                        *DataIO.getInputData(path=os.path.join(self.path_combocode,\
                                                        'Data'),\
                                     keyword='T_DESB',filename='Dust.dat')\
                                    [species_index]/species_tdesa
                    self['T_DESB_' + species] = 10.0**(4)/species_tdesa
                else:
                    self['T_DESA_' + species] = 10.0**(4)\
                        /DataIO.getInputData(path=os.path.join(self.path_combocode,\
                                                        'Data'),\
                                      keyword='T_DES',filename='Dust.dat')\
                                     [species_index]
                    self['T_DESB_' + species] = 10.0**(-4)
        else:
            pass




    def calcR_SHELL_UNIT(self):
        
        '''
        Set default value of R_SHELL_UNIT to R_STAR.
        
        '''
        
        if not self.has_key('R_SHELL_UNIT'):
            self['R_SHELL_UNIT'] = 'R_STAR'
        else:
            pass



    def getAverageDrift(self):
        
        '''
        Return an array with the average drift velocity as a function of 
        radius, from coolfgr_all, in cm/s.
        
        '''

        inputfile = os.path.join(os.path.expanduser('~'),'GASTRoNOoM',\
                self.path_gastronoom,'models',self['LAST_GASTRONOOM_MODEL'],\
                'coolfgr_all' + self['LAST_GASTRONOOM_MODEL'] + '.dat')
        drift = DataIO.getGastronoomOutput(inputfile,keyword='VDRIFT')  
        opa_gs_max = 2.5e-1
        opa_gs_min = 5.0e-3
        return array(drift)/sqrt(0.25)*1.25\
                            *(opa_gs_max**(-2.)-opa_gs_min**(-2.))\
                            /(opa_gs_max**(-2.5)-opa_gs_min**(-2.5))
        


    def calcDENSTYPE(self):
        
        """
        Define the type of density distribution.
        
        Default is 'MASSLOSS' for first iteration, otherwise SHELLFILE.
        
        If second iteration, a DENSFILE is created taking into account the 
        acceleration zone. This file is only created if not already present. 
        
        """
        
        if not self.has_key('DENSTYPE') or not self.has_key('DENSFILE'):
            filename = os.path.join(os.path.expanduser('~'),'GASTRoNOoM',\
                                    self.path_gastronoom,'data_for_mcmax',\
                                    '_'.join(['dens',\
                                              self['LAST_GASTRONOOM_MODEL'],\
                                    'mdotd%.2e.dat'%(self['MDOT_DUST'],)]))
            if os.path.isfile(filename):
                self['DENSFILE'] = filename
                self['DENSTYPE'] = "SHELLFILE"
            else:
                try:
                    if self.has_key('DENSTYPE'):
                        if self['DENSTYPE'] == "MASSLOSS": 
                            raise IOError
                    inputfile = os.path.join(os.path.expanduser('~'),\
                                             'GASTRoNOoM',\
                                             self.path_gastronoom,'models',\
                                             self['LAST_GASTRONOOM_MODEL'],\
                                             'coolfgr_all%s.dat'\
                                             %self['LAST_GASTRONOOM_MODEL'])
                    radius = DataIO.getGastronoomOutput(inputfile)
                    gas_vel = DataIO.getGastronoomOutput(inputfile,\
                                                             keyword='VEL')
                    avgdrift = self.getAverageDrift()             
                    self['DENSTYPE'] = "SHELLFILE"
                    density = float(self['MDOT_DUST'])*self.m_solar\
                                    /((array(gas_vel)+array(avgdrift)) \
                                    *4.*pi*(array(radius)**2.*self.year))
                    self['DENSFILE'] = filename
                    DataIO.writeCols(filename,[array(radius)/self.au,density])        
                    print '** Made MCMax density input file at ' +  filename + '.'
                except IOError:
                    print '** Writing and/or reading DENSFILE output and/or '+\
                          'input failed. Assuming standard mass-loss density'+\
                          ' distribution.'
                    self['DENSTYPE'] = "MASSLOSS"
                    self['DENSFILE'] = ''
        else:
            pass



    def calcDENSFILE(self):
        
        """
        Pointer to the calcDENSTYPE method in case DENSFILE is missing.
    
        """
        
        self.calcDENSTYPE()
        
                            
                                                        
    def calcDUST_LIST(self):
        
        """
        List all non-zero abundances for this star.
    
        """
        
        if not self.has_key('DUST_LIST'):
            self['DUST_LIST'] = [species 
                                 for species in self.species_list 
                                 if self.has_key('A_' + species)]
            self['DUST_LIST'] = [species 
                                 for species in self['DUST_LIST'] 
                                 if float(self['A_' + species]) != 0]
            print 'Dust species that are taken into account during modeling '+\
                  'are %s.'%(', '.join(self['DUST_LIST']))
            print 'The specific density is %.2f g/cm^3.' \
                  %(self['SPEC_DENS_DUST'],)
        else:
            pass
            
            
            
    def calcMOLECULE(self):
        
        '''
        Set the MOLECULE keyword to empty list if not given in the input.
        
        '''
        
        if not self.has_key('MOLECULE'):
            self['MOLECULE'] = []
        else:
            pass
            


    def calcGAS_LIST(self):
        
        """
        Set the GAS_LIST keyword based on the MOLECULE keyword. 
        
        The input MOLECULE format from the CC input is converted into 
        Molecule() objects.
        
        """
        
        if not self.has_key('GAS_LIST') and self['MOLECULE']:
            if len(self['MOLECULE'][0]) == 2:
                #- First convert the long GASTRoNOoM input molecule names to 
                #- the short names, since if len() is 2, it comes from 
                #- PlottingSession.setPacsFromDb
                molec_indices \
                    = [DataIO.getInputData(path=os.path.join(self.path_combocode,\
                                                      'Data'),\
                                    keyword='MOLEC_TYPE',\
                                    filename='Molecule.dat',make_float=0)\
                                   .index(molec[0]) 
                       for molec in self['MOLECULE']]
                molecules_long = [molec[0] for molec in self['MOLECULE']]
                self['MOLECULE'] \
                    = [[DataIO.getInputData(path=os.path.join(self.path_combocode,\
                                                       'Data'),\
                                     keyword='TYPE_SHORT',\
                                     filename='Molecule.dat')[index]] \
                        + [molec[1]] 
                       for molec,index in zip(self['MOLECULE'],molec_indices)]
                self['TRANSITION'] \
                    = [[DataIO.getInputData(path=os.path.join(self.path_combocode,\
                                                       'Data'),\
                                     keyword='TYPE_SHORT',\
                                     filename='Molecule.dat')\
                            [molec_indices[molecules_long.index(trans[0])]]] \
                        + trans[1:]
                       for trans in self['TRANSITION']]
                #- Pull the info from the db
                self['GAS_LIST'] = []
                for molec,model_id in self['MOLECULE']:
                    self['GAS_LIST'].append(Molecule.makeMoleculeFromDb(\
                                        path_combocode=self.path_combocode,\
                                        model_id=model_id,molecule=molec,\
                                        path_gastronoom=self.path_gastronoom))
            else:
                for key,index in zip(['R_OUTER','CHANGE_FRACTION_FILENAME',\
                                             'SET_KEYWORD_CHANGE_ABUNDANCE',\
                                             'NEW_TEMPERATURE_FILENAME',\
                                             'SET_KEYWORD_CHANGE_TEMPERATURE',\
                                             'ENHANCE_ABUNDANCE_FACTOR',\
                                             'ABUNDANCE_FILENAME'],\
                                            [13,16,17,18,19,15,14]):
                    if self['%s_H2O'%key]:
                        self['MOLECULE'] = \
                            [[(i==index and molec[0] in ['1H1H16O','p1H1H16O',\
                                                         '1H1H17O','p1H1H17O',\
                                                         '1H1H18O','p1H1H18O']) 
                                    and self['%s_H2O'%key] 
                                    or str(entry) 
                              for i,entry in enumerate(molec)]
                             for molec in self['MOLECULE']]                          
                self['GAS_LIST'] = \
                    [Molecule.Molecule(\
                        molecule=molec[0],ny_low=int(molec[1]),\
                        ny_up=int(molec[2]),nline=int(molec[3]),\
                        n_impact=int(molec[4]),n_impact_extra=int(molec[5]),\
                        abun_molec=float(molec[6]),\
                        abun_molec_rinner=float(molec[7]),\
                        abun_molec_re=float(molec[8]),\
                        rmax_molec=float(molec[9]),itera=int(molec[10]),\
                        lte_request=int(molec[11]),\
                        use_collis_radiat_switch=int(molec[12]),\
                        abundance_filename=molec[14],\
                        enhance_abundance_factor=float(molec[15]),\
                        path_combocode=self.path_combocode,opr=self['OPR'],\
                        ratio_12c_to_13c=self['RATIO_12C_TO_13C'],\
                        ratio_16o_to_18o=self['RATIO_16O_TO_18O'],\
                        ratio_16o_to_17o=self['RATIO_16O_TO_17O'],\
                        r_outer=float(molec[13]) \
                                    and float(molec[13]) \
                                    or self['R_OUTER_GAS'],\
                        outer_r_mode=float(molec[13]) \
                                        and 'FIXED' \
                                        or self['OUTER_R_MODE'],\
                        dust_to_gas_change_ml_sp=self\
                                                 ['DUST_TO_GAS_CHANGE_ML_SP'],\
                        set_keyword_change_abundance=int(molec[17]),\
                        change_fraction_filename=molec[16],\
                        set_keyword_change_temperature=int(molec[19]),\
                        new_temperature_filename=molec[18])
                     for molec in self['MOLECULE']]
            
            #- safety check
            requested_molecules = set([molec.molecule 
                                      for molec in self['GAS_LIST']])
            if not len(self['GAS_LIST']) == len(requested_molecules): 
                raise IOError('Multiple parameter sets for a single molecule'+\
                              ' passed. This is impossible! Contact Robin...')     
            print 'Gas molecules that are taken into account are ' + \
                  ', '.join(sorted([molec[0] for molec in self['MOLECULE']]))+\
                  '.'        
        elif not self.has_key('GAS_LIST') and not self['MOLECULE']:
            self['GAS_LIST'] = []
        else:
            pass



    def calcR_OUTER_H2O(self):
        
        '''
        Set default value of R_OUTER_H2O to 0.
        
        '''
        
        if not self.has_key('R_OUTER_H2O'):
            self['R_OUTER_H2O'] = 0
        else:
            pass 
      


    def calcNEW_TEMPERATURE_FILENAME_H2O(self):
        
        '''
        Set default value of NEW_TEMPERATURE_FILENAME_H2O to ''.
        
        '''
        
        if not self.has_key('NEW_TEMPERATURE_FILENAME_H2O'):
            self['NEW_TEMPERATURE_FILENAME_H2O'] = ''
        else:
            pass 



    def calcCHANGE_FRACTION_FILENAME_H2O(self):
        
        '''
        Set default value of CHANGE_FRACTION_FILENAME_H2O to ''.
        
        '''
        
        if not self.has_key('CHANGE_FRACTION_FILENAME_H2O'):
            self['CHANGE_FRACTION_FILENAME_H2O'] = ''
        else:
            pass 
      


    def calcSET_KEYWORD_CHANGE_TEMPERATURE_H2O(self):
        
        '''
        Set default value of SET_KEYWORD_CHANGE_TEMPERATURE_H2O to ''.
        
        '''
        
        if not self.has_key('SET_KEYWORD_CHANGE_TEMPERATURE_H2O'):
            self['SET_KEYWORD_CHANGE_TEMPERATURE_H2O'] = 0
        else:
            pass 



    def calcSET_KEYWORD_CHANGE_ABUNDANCE_H2O(self):
        
        '''
        Set default value of SET_KEYWORD_CHANGE_ABUNDANCE_H2O to ''.
        
        '''
        
        if not self.has_key('SET_KEYWORD_CHANGE_ABUNDANCE_H2O'):
            self['SET_KEYWORD_CHANGE_ABUNDANCE_H2O'] = 0
        else:
            pass 
      


    def calcENHANCE_ABUNDANCE_FACTOR_H2O(self):
        
        '''
        Set default value of ENHANCE_ABUNDANCE_FACTOR_H2O to ''.
        
        '''
        
        if not self.has_key('ENHANCE_ABUNDANCE_FACTOR_H2O'):
            self['ENHANCE_ABUNDANCE_FACTOR_H2O'] = 0
        else:
            pass 
      


    def calcABUNDANCE_FILENAME_H2O(self):
        
        '''
        Set default value of ABUNDANCE_FILENAME_H2O to ''.
        
        '''
        
        if not self.has_key('ABUNDANCE_FILENAME_H2O'):
            self['ABUNDANCE_FILENAME_H2O'] = ''
        else:
            pass 
      

    
    def calcR_OUTER_EFFECTIVE(self):
        
        '''
        Get the effective outer radius (either from Mamon, or a fixed value).
        
        '''
        
        filename = os.path.join(os.path.expanduser('~'),'GASTRoNOoM',\
                                self.path_gastronoom,'models',\
                                self['LAST_GASTRONOOM_MODEL'],\
                                'input%s.dat'%self['LAST_GASTRONOOM_MODEL'])
        
        if not self.has_key('R_OUTER_EFFECTIVE'):
            self['R_OUTER_EFFECTIVE'] \
                = float(DataIO.readFile(filename=filename,delimiter=' ')[0][4])
        else:
            pass



    def calcKEYWORD_DUST_TEMPERATURE_TABLE(self):
        
        '''
        Set KEYWORD_DUST_TEMPERATURE_TABLE to False for now. 
        
        If it was not yet defined, there is not ftemperature file anyway.
        
        '''
        
        if not self.has_key('KEYWORD_DUST_TEMPERATURE_TABLE'):
            if self['DUST_TEMPERATURE_FILENAME']:
                self['KEYWORD_DUST_TEMPERATURE_TABLE'] = 1
            else:
                self['KEYWORD_DUST_TEMPERATURE_TABLE'] = 0
        else:
            pass
    

    
    def calcNUMBER_INPUT_DUST_TEMP_VALUES(self):
        
        '''
        Set NUMBER_INPUT_DUST_TEMP_VALUES to length of input file for dust temp 
        
        If it does not exist set to 0.
        
        '''
        
        if not self.has_key('NUMBER_INPUT_DUST_TEMP_VALUES'):
            if self['DUST_TEMPERATURE_FILENAME']:
                self['NUMBER_INPUT_DUST_TEMP_VALUES'] \
                    = len([1 
                           for line in DataIO.readFile(\
                                            self['DUST_TEMPERATURE_FILENAME']) 
                           if line])
            else:
                self['NUMBER_INPUT_DUST_TEMP_VALUES'] = 0
        else:
            pass  

    
                            
    def calcDUST_TEMPERATURE_FILENAME(self):
        
        """
        Look for the temperature stratification of the star.
    
        If a last mcmax model is available, the filename is given, (for now 2d). 
        
        Else an empty string is given, and a power law is used in GASTRoNOoM.
        
        """
        
        if not self.has_key('DUST_TEMPERATURE_FILENAME'):
            filename = self['RID_TEST'] != 'R_STAR' \
                            and os.path.join(os.path.expanduser('~'),'MCMax',\
                                             self.path_mcmax,\
                                             'data_for_gastronoom',\
                                             '_'.join(['Td',\
                                                     self['LAST_MCMAX_MODEL'],\
                                                     self['RID_TEST']\
                                                      +'.dat']))\
                            or os.path.join(os.path.expanduser('~'),'MCMax',\
                                            self.path_mcmax,\
                                            'data_for_gastronoom',\
                                            '_'.join(['Td',\
                                                      self['LAST_MCMAX_MODEL']\
                                                      + '.dat']))
            if os.path.isfile(filename):
                self['DUST_TEMPERATURE_FILENAME'] = filename
            else:
                try:
                    rad_list = array(self.getMCMaxOutput(int(self['NRAD'])))\
                                     /self.r_solar/float(self['R_STAR'])
                    temp_list = self.getMCMaxOutput(int(self['NRAD'])\
                                                    *int(self['NTHETA']),\
                                                    keyword='TEMPERATURE')
                    t_strat = Data.reduceArray(temp_list,self['NTHETA'])
                    if self['RID_TEST'] == 'R_STAR':
                         t_strat = t_strat[rad_list > 1]
                         rad_list = rad_list[rad_list > 1]
                    elif self['RID_TEST'] == 'R_INNER_GAS':
                         t_strat = t_strat[rad_list > self['R_INNER_GAS']]
                         rad_list = rad_list[rad_list > self['R_INNER_GAS']]
                    elif self['RID_TEST'] == 'BUGGED_CASE':
                         t_strat = t_strat[rad_list > self['R_STAR']]
                         rad_list = rad_list[rad_list > self['R_STAR']]
                    self['DUST_TEMPERATURE_FILENAME'] = filename
                    DataIO.writeCols(filename,[array(rad_list),t_strat])
                    self['KEYWORD_DUST_TEMPERATURE_TABLE'] = 1
                    self['NUMBER_INPUT_DUST_TEMP_VALUES'] = len(rad_list)
                    print '** Made dust temperature stratifaction file at %s.'\
                          %filename
                except IOError:
                    self['DUST_TEMPERATURE_FILENAME'] = ''
        else:
            pass                        
                              
  
                            
    def calcGAS_LINES(self):
        
        """
        Making transition line input for gas data (auto search) 
        and additional no-data lines.
        
        The Transition() objects are created then for these lines and added
        to the GAS_LINES list.
    
        """

        if not self.has_key('GAS_LINES'):
            self['GAS_LINES'] = tuple()
            #- To make sure the GAS_LIST is done, and the conversion of 
            #- TRANSITION to the right molecule names is done 
            #- (in case of PlottingSession.setPacsFromDb is used)
            self.calcGAS_LIST()     
            if self['PATH_GAS_DATA'] and self['DATA_MOL']:
                searchpath = os.path.join(self['PATH_GAS_DATA'],
                                         self['STAR_NAME_GASTRONOOM'] + '_*.*')
                raw_data_list = [f 
                                 for f in glob(searchpath)
                                 if os.path.splitext(f)[1][-1] != '~']
                raw_data_list = sorted(raw_data_list,key=\
                    lambda x: os.path.splitext(x.replace\
                                (self['STAR_NAME_GASTRONOOM']+'_','',1))[0]\
                                .split('_')[0] \
                            + os.path.splitext(x.replace \
                                (self['STAR_NAME_GASTRONOOM'] + '_','',1))[0]\
                                .split('_')[-1])
                data_list = [os.path.splitext(os.path.split(f)[1])[0].replace \
                                (self['STAR_NAME_GASTRONOOM'] + '_','',1)\
                                .split('_')
                             for f in raw_data_list] 
                data_list = sorted([data_molec + [molec] + [raw]
                                    for raw,data_molec in zip(raw_data_list,\
                                                              data_list)
                                    for molec in self['GAS_LIST'] 
                                    if data_molec[0]\
                                            [0:len(molec.molecule_short)] \
                                        == molec.molecule_short],\
                                   key=operator.itemgetter(0))
                trans_list = [Transition.Transition(\
                                    datafiles=molec.pop(),\
                                    molecule=molec.pop(),\
                                    telescope=molec.pop(),\
                                    jup=int(molec[0][-2]),\
                                    jlow=int(molec[0][-1]),\
                                    n_quad=self['N_QUAD'],\
                                    use_maser_in_sphinx=self\
                                                      ['USE_MASER_IN_SPHINX'],\
                                    path_combocode=self.path_combocode,\
                                    path_gastronoom=self.path_gastronoom)
                               for molec in data_list]
                self['GAS_LINES'] = Transition.checkUniqueness(trans_list)
                self.updateSelectTargetData(raw_data_list)
            #- Check if specific transition were requested in addition to data
            if self.has_key('TRANSITION'):
                self['TRANSITION'] = [trans 
                                      for trans in self['TRANSITION'] 
                                      if trans[0] in [molec[0] 
                                                      for molec in self\
                                                                 ['MOLECULE']]]
                new_lines = [Transition.makeTransition(self,trans) 
                             for trans in self['TRANSITION']]
                new_lines.extend(self['GAS_LINES'])
                self['GAS_LINES'] = tuple(set(new_lines))
            #- Check if molecular line catalogues have to be browsed to create 
            #- line lists in addition to the data
            if self['LINE_LISTS']:
                if self['LINE_LISTS'] == 1: self.addLineList()
                elif self['LINE_LISTS'] == 2: 
                    ll_filename = os.path.split(self['LL_FILE'].strip())[0] \
                            and self['LL_FILE'].strip() \
                            or os.path.join(os.path.expanduser('~'),\
                                            'GASTRoNOoM','LineLists',\
                                            os.path.split(self['LL_FILE']\
                                                                .strip())[1])
                    lines = [line.split() 
                            for line in DataIO.readFile(ll_filename) 
                            if line[0] != '#' \
                              and line.split()[0].replace('TRANSITION=','') in \
                                  [molec[0] for molec in self['MOLECULE']]]
                    new_lines = [Transition.makeTransition(self,line) 
                                 for line in lines]
                    new_lines.extend(self['GAS_LINES'])
                    self['GAS_LINES'] = tuple(set(new_lines))
            self['GAS_LINES'] = sorted(list(self['GAS_LINES']),\
                                       key=lambda x: str(x))
            requested_transitions = set([str(trans) 
                                         for trans in self['GAS_LINES']]) 
            if not len(self['GAS_LINES']) == len(requested_transitions):
                print 'Length of the requested transition list: %i'\
                      %len(self['GAS_LINES'])
                print 'Length of the requested transition list with only ' + \
                      'the "transition string" parameters: %i'\
                      %len(requested_transitions)
                print 'Guilty transitions:'
                trans_strings = [str(trans) for trans in self['GAS_LINES']]
                print '\n'.join([str(trans) 
                                 for trans in self['GAS_LINES'] 
                                 if trans_strings.count(str(trans))>1])
                raise IOError('Multiple parameter sets for a single ' + \
                              'transition requested. This is impossible! '+ \
                              'Check code/contact Robin.')
        else:
            pass



    def calcSTARTYPE(self):
        
        """
        Set the default value for STARTYPE, which is the blackbody 
        assumption (BB). Currently only for MCMax.
        
        """
        
        if not self.has_key('STARTYPE'):
            self['STARTYPE'] = 'BB'
        else:
            pass



    def calcSTARFILE(self):
        
        """
        Set the default value for STARFILE, which is an empty string 
        (ie STARTYPE is BB, no inputfile). Currently only for MCMax.
        
        """
        
        if not self.has_key('STARFILE'):
            self['STARFILE'] = ''
        else:
            pass



    def updateSelectTargetData(self,raw_data_list):
        
        ''' 
        Updating select_target_data.pro if necessary.
        
        @param raw_data_list: sorted filenames of the data in PATH_GAS_DATA
        @type raw_data_list: list[string]
                
        '''
        
        filename = os.path.join(os.path.expanduser('~'),'GASTRoNOoM',\
                                'scripts','select_target_data.pro')
        select_target_data = DataIO.readFile(filename=filename)
        i = 0
        while True:
            if select_target_data[i].find('stars=[') != -1: break
            i += 1
        stars_list = [starname.strip("'") 
                      for starname in select_target_data[i].rstrip(']')\
                                          .replace('stars=[','',1).split(',')
                      if starname]
        try:
            #- Is the star present? Then no error, and star_presence will be 
            #- put to True
            star_presence = False
            which_star = stars_list.index(self['STAR_NAME_GASTRONOOM'])
            star_presence = True
            j = 0
            while True:
                j += 1
                if select_target_data[i+j]\
                        .find('files_' + self['STAR_NAME_GASTRONOOM']) != -1: 
                    break
            starnames = select_target_data[i+j].rstrip(']').replace('files_'+\
                           self['STAR_NAME_GASTRONOOM'] + '=[','',1).split(',')
            files_list = [starname.strip("'") for starname in starnames]
            if len(files_list) != len(raw_data_list) \
                    or float(select_target_data[i+j+1].split('=')[1]) \
                                != self['V_LSR'] \
                    or float(select_target_data[i+j+2].split('=')[1]) \
                                != self['VEL_INFINITY_GAS']:
                raise ValueError
        except ValueError:
            #- add star to the list and find star_information entry point
            if not star_presence:
                stars_list.append(self['STAR_NAME_GASTRONOOM'])
                select_target_data[i:i] = ['stars=[' \
                                           + ','.join(["'" + starname + "'" 
                                                  for starname in stars_list])\
                                           + ']']
                del select_target_data[i+1]
                j = 0
                while True:
                    if select_target_data[i+j+1]\
                            .find('remarks,extra=extra,remarks=remarks') != -1:
                        break
                    j += 1
            select_target_data[i+j:i+j] \
                    = ['files_' + self['STAR_NAME_GASTRONOOM'] + \
                       '=[' + ','.join(["'" + os.path.split(f)[1] + "'" 
                                        for f in raw_data_list]) + \
                       ']']
            select_target_data[i+j+1:i+j+1] \
                    = ['vlsr_' + self['STAR_NAME_GASTRONOOM'] + \
                       '=' + str(float(self['V_LSR']))]
            select_target_data[i+j+2:i+j+2] \
                    = ['vinfty_' + self['STAR_NAME_GASTRONOOM'] + \
                       '=' + str(float(self['VEL_INFINITY_GAS']))]
            select_target_data[i+j+3:i+j+3] = [' ']
            if star_presence:
                for k in range(4):
                    del select_target_data[i+j+4]
            DataIO.writeFile(os.path.join(os.path.expanduser('~'),\
                                          'GASTRoNOoM','scripts',\
                                          'select_target_data.pro'),\
                             select_target_data)



    def calcLINE_LISTS(self):
        
        ''' 
        If the LINE LISTS keyword is not present, set to False.
        
        '''
        
        if not self.has_key('LINE_LISTS'):
            self['LINE_LISTS'] = 0
        else:
            pass



    def calcDUST_TO_GAS(self):
        
        '''
        Calculate the empirical value oft he dust to gas ratio.
        
        '''
        
        if not self.has_key('DUST_TO_GAS'):
            self['DUST_TO_GAS'] = float(self['MDOT_DUST'])\
                                    *float(self['VEL_INFINITY_GAS'])\
                                    /float(self['MDOT_GAS'])\
                                    /float(self['V_EXP_DUST'])
        else:
            pass


  
    def calcDUST_TO_GAS_INITIAL(self):
        
        '''
        Set a default value for the initial dust-to-gas ratio at 0.002.
        
        '''
        
        if not self.has_key('DUST_TO_GAS_INITIAL'):
            self['DUST_TO_GAS_INITIAL'] = 0.002
        else:
            pass  



    def calcDUST_TO_GAS_ITERATED(self):
        
        '''
        Fetch the iterated result of the dust-to-gas ratio from cooling.
        
        '''
        
        if not self.has_key('DUST_TO_GAS_ITERATED'):
            try:
                filename = os.path.join(os.path.expanduser('~'),'GASTRoNOoM',\
                                        self.path_gastronoom,'models',\
                                        self['LAST_GASTRONOOM_MODEL'],\
                                        'input%s.dat'\
                                        %self['LAST_GASTRONOOM_MODEL'])
                self['DUST_TO_GAS_ITERATED'] = float(DataIO.readFile(\
                                                        filename=filename,\
                                                        delimiter=' ')[0][6])
            except IOError:
                self['DUST_TO_GAS_ITERATED'] = None
        else:
            pass  



    def getOpticalDepth(self,wavelength=0):
        
        '''
        Calculate the optical depth.
        
        If wavelength keyword is given, tau at wavelength is returned. 
        
        Otherwise, the full wavelength array is returned.
        
        @keyword wavelength: the wavelength in micron. If 0, the whole 
                             wavelength array is returned.
                             
                             (default: 0)
        @type wavelength: float
        
        @return: The optical depth at requested wavelength or the full
                 wavelength and optical depth arrays
        @rtype: float or (array,array)
        
        '''
        
        wavelength = float(wavelength)
        radius = array(self.getMCMaxOutput(int(self['NRAD'])))
        dens = self.getMCMaxOutput(int(self['NRAD'])*int(self['NTHETA']),\
                                   keyword='DENSITY')
        dens = Data.reduceArray(dens,self['NTHETA'])
        wave_list,kappas = self.readWeightedKappas()
        if wavelength:
            wave_index = argmin(abs(wave_list-wavelength))
            return integrate.trapz(y=dens*kappas[wave_index],x=radius)
        else:
            return (wave_list,array([integrate.trapz(y=dens*kappas[i],x=radius)
                                     for i in xrange(len(wave_list))]))
        
        
    
    def readWeightedKappas(self):
        
        '''
        Return the wavelength and kappas weighted with their respective dust 
        mass fractions.
        
        @return: The wavelength and weighted kappas grid
        @rtype: (array,array)
        
        '''
        
        wave_list,kappas = self.readKappas()
        wkappas = [sum([float(self['A_%s'%(species)])*float(kappas[i][j])
                      for i,species in enumerate(self['DUST_LIST']*2)])
                   for j in xrange(len(kappas[0]))]
        return array(wave_list),array(wkappas)
        
        
    
    def calcRATIO_12C_TO_13C(self):
        
        '''
        Set default value for ratio_12c_to_13c to 0.
        
        '''
        
        if not self.has_key('RATIO_12C_TO_13C'):  
            self['RATIO_12C_TO_13C'] = 0
        else:
            pass
    


    def calcRATIO_16O_TO_17O(self):
        
        '''
        Set default value for ratio_16o_to_17o to 0.
        
        '''
        
        if not self.has_key('RATIO_16O_TO_17O'):  
            self['RATIO_16O_TO_17O'] = 0
        else:
            pass
            


    def calcRATIO_16O_TO_18O(self):
        
        '''
        Set default value for ratio_16o_to_18o to 0.
        
        '''
        
        if not self.has_key('RATIO_16O_TO_18O'):  
            self['RATIO_16O_TO_18O'] = 0
        else:
            pass    
        


    def calcOPR(self):
        
        '''
        Set default value for opr to 0.
        
        '''
        
        if not self.has_key('OPR'):  
            self['OPR'] = 0
        else:
            pass                
        


    def calcUSE_NEW_DUST_KAPPA_FILES(self):
        
        '''
        Set the default value of USE_NEW_DUST_KAPPA_FILES to 1.
        
        '''
        
        if not self.has_key('USE_NEW_DUST_KAPPA_FILES'):  
            self['USE_NEW_DUST_KAPPA_FILES'] = 1
        else:
            pass         



    def calcTEMDUST_FILENAME(self):
        
        """
        Making extinction efficiency input files for GASTRoNOoM from MCMax 
        output mass extinction coefficients.
        
        If no MCMax output available, this file is temdust.kappa, the standard.
        
        In units of cm^-1, Q_ext/a.
        
        """
        
        if not self.has_key('TEMDUST_FILENAME'):
            if self['NLAM'] > 2000:
                #- For now not supported, GASTRoNOoM cannot take more than 2000
                #- wavelength opacity points
                raise IOError('NLAM > 2000 not supported due to GASTRoNOoM '+\
                              'opacities!')    
            filename = os.path.join(os.path.expanduser('~'),'GASTRoNOoM',\
                                    'src','data','temdust_%s.dat'\
                                    %self['LAST_MCMAX_MODEL'])
            if not int(self['USE_NEW_DUST_KAPPA_FILES']) \
                    or not self['LAST_MCMAX_MODEL']:
                self['TEMDUST_FILENAME'] = 'temdust.kappa'
            elif os.path.isfile(filename):
                self['TEMDUST_FILENAME'] = os.path.split(filename)[1]
            else:
                try:
                    wavelength,q_ext = self.readWeightedKappas()
                    q_ext *= self['SPEC_DENS_DUST']*(4.0/3)
                    wavelength = list(wavelength)
                    wavelength.reverse()
                    q_ext = list(q_ext)
                    q_ext.reverse()
                    self['TEMDUST_FILENAME'] = os.path.split(filename)[1]
                    DataIO.writeCols(filename,[wavelength,q_ext])
                    print '** Made opacity file at ' + filename + '.'
                except IOError:
                    self['TEMDUST_FILENAME'] = 'temdust.kappa'
        else:
            pass    
     
    
    
    def calcR_OH1612_AS(self):
         
        '''
        Set the R_OH1612_AS to the default value of 0 as.
        
        '''
        
        if not self.has_key('R_OH1612_AS'):  
            self['R_OH1612_AS'] = 0
        else:
            pass


    
    def calcR_OH1612(self):
         
        '''
        Calculate the R_OH1612 in R_STAR.
        
        '''
        
        if not self.has_key('R_OH1612'):  
            self['R_OH1612'] = Data.convertAngular(self['R_OH1612_AS'],\
                                                   self['DISTANCE'])\
                                    /self['R_STAR']/self.r_solar
        else:
            pass         


    
    def calcR_OH1612_NETZER(self):
         
        '''
        Calculate the radial OH maser peak distance in cm.
        
        Taken from Netzer & Knapp 1987, eq. 29. 
        
        The interstellar radiation factor is taken as A = 5.4 
        (avg Habing Field)

        '''
        
        if not self.has_key('R_OH1612_NETZER'):  
            mg = self['MDOT_GAS']/1e-5
            vg = self['VEL_INFINITY_GAS']
            self['R_OH1612_NETZER'] = ((5.4*mg**0.7/vg**0.4)**-4.8\
                                        + (74.*mg/vg)**-4.8)**(-1/4.8)*1e16\
                                        /self['R_STAR']/self.r_solar
        else:
            pass         
    
    
    
    def getBlackBody(self):
        
        '''
        Calculate the black body intensity profile.
        
        @return: The wavelength and black body intensity grid
        @rtype: (array,array)
        
        '''
        
        #- Define wavelength grid in cm
        w = 10**(linspace(-9,2,5000))
        freq = self.c/w
        #- Calculate the blackbody
        bb = 2*self.h*freq**3/self.c**2 * \
             (1/(exp((self.h*freq)/(self.k*self['T_STAR']))-1))
        return w*10**(4),bb*10**(23)
    
    
    
    def getObservedBlackBody(self):
        
        '''
        Scale the blackbody intensity following the distance and stellar radius.
        
        This is not the flux!
        
        @return: The wavelength grid and rescaled blackbody intensity
        @rtype: (array,array)
        
        '''
        
        w,bb = self.getBlackBody()
        return w,bb*(self['R_STAR']*self.r_solar)**2\
                   /(self['DISTANCE']*self.pc)**2
        


    def missingInput(self,missing_key):
        
        """
        Try to resolve a missing key.
        
        @param missing_key: the missing key for which an attempt will be made 
                            to calculate its value based on already present 
                            parameters
        @type missing_key: string
        
        """
        
        if missing_key in ('T_STAR','L_STAR','R_STAR'):
            self.calcTLR()
        elif missing_key in ('A_K','V_LSR','STAR_NAME_PLOTS',\
                             'STAR_NAME_GASTRONOOM','LONG','LAT'):
            self.getClassAttr(missing_key)
        elif missing_key in ['R_MAX_' + species 
                             for species in self.species_list]:
            self.calcR_MAX(missing_key)
        elif missing_key in ['R_DES_' + species 
                             for species in self.species_list]:
            self.checkT()
        elif missing_key in ['T_DESA_' + species 
                             for species in self.species_list] + \
                            ['T_DESB_' + species 
                             for species in self.species_list]:
            self.calcT_DES(missing_key[7:])
        elif missing_key in ['T_DES_' + species 
                             for species in self.species_list]:
            self.checkT()
        elif hasattr(self,'calc' + missing_key):
            getattr(self,'calc' + missing_key)()
        else:
            pass
