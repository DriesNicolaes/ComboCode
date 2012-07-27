# -*- coding: utf-8 -*-

"""
Toolbox for Transitions, used in various applications concerning GASTRoNOoM.

Author: R. Lombaert

"""

import os 
import re
from scipy import pi, exp, linspace, argmin, array
from scipy.interpolate import interp1d
from scipy.integrate import trapz
import types

from cc.modeling.objects import Molecule 
from cc.tools.io import Database, DataIO
from cc.tools.io import SphinxReader
from cc.tools.io import FitsReader, TxtReader
from cc.tools.numerical import Interpol
from cc.statistics.BasicStats import calcChiSquared, calcLoglikelihood


def extractTransFromStars(star_grid,sort_freq=1,sort_molec=1,pacs=0):
    
    '''
    Extract a list a of unique transitions included in a list of Star() objects
    and sort them.
    
    An extra flag is added to the input keyword to determine inclusion of PACS
    lines or not.
    
    The list of transitions is copies to make sure no funky references mess 
    with the original transitions.
    
    @param star_grid: The list of Star() objects from which all 'GAS_LINES' 
                       keys are taken and collected in a set. 
    @type star_grid: list[Star()]
    
    @keyword sort_freq: Sort the transitions according to their frequencies. 
                        Otherwise, they are sorted by their wavelengths.
    
                        (default: 1)
    @type sort_freq: bool
    @keyword sort_molec: Sort the transitions by molecule first.
                      
                         (default: 1) 
    @type sort_molec: bool
    @keyword pacs: 1: Only select PACS lines. 0: Don't select PACS lines. 2: Do
                      not make a distinction between the telescope type.
                      
                      (default: 0)
    @type pacs: int
    
    @return: a list of unique transitions included in all Star() objects in
             star_grid
    @rtype: list[Transition()]
    
    '''
    
    pacs = int(pacs)
    selection = list(sorted(set([trans 
                                 for star in star_grid
                                 for trans in star['GAS_LINES']]),\
                            key=lambda x:sort_freq \
                                and (sort_molec and x.molecule or '',\
                                     x.frequency) \
                                or  (sort_molec and x.molecule or '',\
                                     x.wavelength)))
    if not pacs:
        return [trans for trans in selection if 'PACS' not in trans.telescope]
    if pacs == 1:
        return [trans for trans in selection if 'PACS' in trans.telescope]
    else:
        return selection



def updateLineSpec(trans_list):
    
    '''
    Update telescope.spec file.
    
    This method checks for requested transitions that are not yet present in 
    .spec file of the telescope, and adds them.
    
    @param trans_list: The transitions in the CC input
    @type trans_list: list[Transition()]
    
    '''
    
    telescopes = list(set([trans.telescope for trans in trans_list]))
    for telescope in telescopes:
        if not ('HIFI' in telescope or 'PACS' in telescope):
            print 'Warning! Telescope beam efficiencies for %s'%telescope + \
                  ' are added arbitrarily and thus are not the correct values.'
        old_spec = DataIO.readFile(os.path.join(os.path.expanduser('~'),\
                                  'GASTRoNOoM','src','data',telescope+'.spec'))
        line_spec_list = [line 
                          for line in old_spec 
                          if line.find('LINE_SPEC') >-1 and line[0] != '#']
        these_trans = [trans 
                       for trans in trans_list 
                       if trans.telescope == telescope]
        these_trans = [trans.getLineSpec() 
                       for trans in these_trans 
                       if trans.getLineSpec() not in line_spec_list]
        line_spec_list = sorted(line_spec_list + these_trans,\
                              key=lambda x: [x.split()[0],float(x.split()[9])])
        line_spec_list = [line.replace(' ','\t') for line in line_spec_list]
        try:
            line_spec_index = [line[0:9] 
                               for line in old_spec].index('LINE_SPEC')
            new_spec = old_spec[0:line_spec_index] + line_spec_list
        except ValueError:
            new_spec = old_spec + line_spec_list
        DataIO.writeFile(os.path.join(os.path.expanduser('~'),'GASTRoNOoM',\
                                      'src','data',telescope+'.spec'),\
                         new_spec+['\n######################################'])

 

def makeTransition(star,trans):
    
    '''
    Create a Transition instance based on a Star object and a standard CC input 
    line, with 12 entries in a list.
    
    @param star: The star object providing basic info
    @type star: Star()
    @param trans: the input line with 12 entries, the first being the molecule,
                  followed by all 11 CC input parameters for a transition
    @type trans: list[string]
    
    @return: The transition object is returned with all info included
    @rtype: Transition()
    
    '''
    
    molec = star.getMolecule(trans[0].replace('TRANSITION=',''))
    if molec <> None:
        return Transition(molecule=molec,\
                          vup=int(trans[1]),jup=int(trans[2]),\
                          kaup=int(trans[3]),kcup=int(trans[4]),\
                          vlow=int(trans[5]),jlow=int(trans[6]),\
                          kalow=int(trans[7]),kclow=int(trans[8]),\
                          telescope=trans[9],offset=float(trans[10]),\
                          n_quad=int(trans[11]),vexp=star['VEL_INFINITY_GAS'],\
                          path_combocode=star.path_combocode,\
                          use_maser_in_sphinx=star['USE_MASER_IN_SPHINX'],\
                          path_gastronoom=star.path_gastronoom)
    else:
        return None    
        


def makeTransitionFromSphinx(filename,path_combocode=os.path.join(os.path\
                                            .expanduser('~'),'ComboCode')):
    
    '''
    Make a Transition() based on the filename of a Sphinx file.
    
    For this information is taken from the Molecule() model database.
    
    @param filename: The sphinx file name, including path
    @type filename: string
    
    @keyword path_combocode: The CC home folder
    
                             (default: ~/ComboCode/)
    @type path_combocode: string
    
    @return: The transition
    @rtype: Transition()
    
    '''
    
    filepath,filename = os.path.split(filename)
    if not filepath:
        raise IOError('Please include the full filepath of the Sphinx ' + \
                      'filename, needed to determine the name of the database.')
    
    #- clip model_id and save it into trans_id
    filepath,trans_id = os.path.split(filepath)
    #- clip 'models'
    filepath = os.path.split(filepath)[0]
    #- clip path_gastronoom and save it in path_gastronoom
    filepath,path_gastronoom = os.path.split(filepath)
    
    if os.path.isfile(os.path.join(filepath,'cooling_id.log')):
        model_id = DataIO.readFile(os.path.join(filepath,'cooling_id.log'))[0]
        #- If an mline_id.log exists, a cooling_id.log will always exist also
        if os.path.isfile(os.path.join(filepath,'mline_id.log')):
            molec_id = DataIO.readFile(os.path.join(filepath,'mline_id.log'))[0]
        else: #- ie trans id is the same as molec id, first trans calced for id
            molec_id = trans_id
    #- ie mline and trans id are same as model id, first calced for id
    else: 
        model_id = trans_id
        molec_id = trans_id
        
    filename = filename.rstrip('.dat').split('_')[2:]
    molec_name = filename.pop(0)
    molec = Molecule.makeMoleculeFromDb(molecule=molec_name,molec_id=molec_id,\
                                        path_gastronoom=path_gastronoom,\
                                        path_combocode = path_combocode)
    telescope = filename.pop(-2)
    pattern = re.compile(r'^(\D+)(\d*.?\d*)$')
    numbers = [pattern.search(string).groups() for string in filename]
    numbers = dict([(s.lower(),n) for s,n in numbers])
    trans = Transition(molecule=molec,telescope=telescope,\
                       path_combocode=path_combocode,\
                       path_gastronoom=path_gastronoom,**numbers)
    trans.setModelId(trans_id)
    trans_db = Database.Database(os.path.join(filepath,path_gastronoom,\
                                              'GASTRoNOoM_sphinx_models.db'))
    trans_dict = trans_db[model_id][molec_id][trans_id][str(trans)].copy()
    [setattr(trans,k.lower(),v)
            for k,v in trans_dict.items()
            if k != 'TRANSITION']
    return trans



def checkUniqueness(trans_list):
    
    '''
    Check uniqueness of a list of transitions.
    
    Same transitions are replaced by a single transition with all datafiles 
    from the originals. 
    
    Based on the parameters of the transitions. If they are the same, only one
    transition is added to the output list, but the datafiles are all included.
    
    Datafiles do not identify a transition!
    
    @param trans_list: The transitions to be checked for uniqueness
    @type trans_list: list[Transition()]
    
    @return: The merged transitions with all datafiles included.
    @rtype: tuple[Transition()]
    
    '''
    
    merged = []
    for trans in trans_list:
        if trans not in merged: 
            merged.append(trans)
        else:
            merged[merged.index(trans)].addDatafile(trans.datafiles)
    return merged
    
    

class Transition():
    
    '''
    A class to deal with transitions in GASTRoNOoM.
    
    '''
    
    def __init__(self,molecule,telescope=None,vup=0,jup=0,kaup=0,kcup=0,\
                 nup=None,vlow=0,jlow=0,kalow=0,kclow=0,nlow=None,offset=0.0,\
                 frequency=None,exc_energy=None,int_intensity_log=None,\
                 n_quad=100,use_maser_in_sphinx=0,vexp=None,\
                 vibrational='',path_gastronoom=None,datafiles=None,\
                 path_combocode=os.path.join(os.path.expanduser('~'),\
                                             'ComboCode')):
        
        '''
        
        Initiate a Transition instance, setting all values for the 
        quantummechanical parameters to zero (by default).
        
        @param molecule: The molecule to which this transition belongs
        @type molecule: Molecule()
        
        @keyword telescope: The telescope with which the transition is observed
        
                            (default: None)
        @type telescope: string
        @keyword vup: The upper vibrational level
        
                      (default: 0)
        @type vup: int
        @keyword jup: The upper rotational level
        
                      (default: 0)
        @type jup: int
        @keyword kaup: The upper level of the first projection of the ang mom
        
                       (default: 0)
        @type kaup: int       
        @keyword kcup: The upper level of the second projection of the ang mom
        
                       (default: 0)
        @type kcup: int
        @keyword nup: if not None it is equal to Kaup and only relevant for 
                      SO/hcn-type molecules
        
                      (default: 0)
        @type nup: int
        @keyword vlow: The lower vibrational level
        
                       (default: 0)
        @type vlow: int
        @keyword jlow: The lower rotational level
        
                       (default: 0)
        @type jlow: int
        @keyword kalow: The lower level of the first projection of the ang mom
        
                        (default: 0)
        @type kalow: int
        @keyword kclow: The lower level of the second projection of the ang mom
        
                        (default: 0)
        @type kclow: int
        @keyword nlow: if not None it is equal to Kalow, and only relevant for 
                       SO-type molecules
        
                       (default: None)
        @type nlow: int
        @keyword offset: The offset of the radiation peak with respect to the 
                         central pixel of the observing instrument. Only 
                         relevant for non-point corrected PACS or non Pacs data
                         (so not relevant when INSTRUMENT_INTRINSIC=1)
                         
                         (default: 0.0)
        @type offset: float
        @keyword path_combocode: CC home folder
        
                                 (default: '~/ComboCode/')
        @type path_combocode: string
        @keyword n_quad: Number of impact par. in quadrature int(Inu pdp).
                         Relevant for the ray-tracing of the line profiles
        
                         (default: 100)
        @type n_quad: int
        @keyword use_maser_in_spinx: using maser calc in sphinx code
                                     
                                     (default: 0)
        @type use_maser_in_spinx: bool
        @keyword vexp: The terminal gas expansion velocity. Used only to 
                       determine noise levels in the datasets
                       
                       (default: None)
        @type vexp: float
        @keyword frequency: if not None the frequency of the transition is 
                            taken to be this parameter in Hz, if None the 
                            frequency of this transition is derived from the 
                            GASTRoNOoM radiative input file
                            
                            No indices are searched for if frequency is given 
                            here. Usually used only for line listing.
                            
                            (default: None)
        @type frequency: float
        @keyword exc_energy: the excitation energy (cm-1, from CDMS/JPL) if you
                             want it included in the Transition() object, 
                             not mandatory!
                             
                             (default: None)
        @type exc_energy: float                     
        @keyword int_intensity_log: the integrated intensity of the line in 
                                    logscale from CDMS/JPL, if you want it 
                                    included in the Transition() object, 
                                    not mandatory!
                                    
                                    (default: None)
        @type int_intensity_log: float
        @keyword vibrational: In the case of line lists, this keyword indicates
                              the type of vibrational excitation, relevant fi 
                              for H2O. Empty string if vibrational groundstate
                              
                              (default: '')
        @type vibrational: string
        @keyword path_gastronoom: model output folder in the GASTRoNOoM home
        
                                  (default: None)
        @type path_gastronoom: string
        @keyword datafiles: (multiple) filename(s) and path(s) to a datafile 
                            for transition, specific for the telescope used for 
                            this dataset. Only applicable for single transition 
                            files, such as ground-based data. None if no files 
                            available.
                                    
                            (default: None)
        @type datafiles: string/list
        
        '''
        
        self.molecule = molecule
        if telescope is None:
            self.telescope = 'N.A.'
        else:
            self.telescope = telescope.upper()
        self.vup = int(vup)
        self.jup = int(jup)
        self.kaup = int(kaup)
        self.kcup = int(kcup)
        self.vlow = int(vlow)
        self.jlow = int(jlow)
        self.kalow = int(kalow)
        self.kclow = int(kclow)
        self.offset = float(offset)
        self.path_combocode = path_combocode
        self.n_quad = int(n_quad)
        self.use_maser_in_sphinx = int(use_maser_in_sphinx)
        self.vexp = vexp
        self.__model_id = None
        if nup is None or nlow is None:
            self.nup = self.kaup            
            self.nlow = self.kalow
            #- In case of SO, the quantum number is treated as Kaup/low but is
            #- in fact Nup/low
        self.exc_energy = exc_energy
        self.int_intensity_log = int_intensity_log
        self.vibrational = vibrational
        self.sphinx = None
        self.path_gastronoom = path_gastronoom
        if type(datafiles) is types.StringType:
            self.datafiles = [datafiles]
        else:
            self.datafiles = datafiles
        self.lpdata = None 
        self.radiat_trans = None
        if frequency is None:
            self.__setIndices()     #sets frequency from GASTRoNOoM input in s^-1
        else:
            self.frequency = frequency
        self.wavelength = 2.99792458e10/self.frequency  #in cm
        self.best_vlsr = None
        
        
        
    def __str__(self):
        
        '''
        Printing a transition as it should appear in the GASTRoNOoM input file.
        
        @return: The Transition string
        @rtype: string
        
        '''
        
        return 'TRANSITION=%s %i %i %i %i %i %i %i %i %s %.2f' \
               %(self.molecule.molecule_full,self.vup,self.jup,self.kaup,\
                 self.kcup,self.vlow,self.jlow,self.kalow,self.kclow,\
                 self.telescope,self.offset)
                    


    def __eq__(self,other):
        
        '''
        Compare two transitions and return true if equal.
        
        The condition is the dictionary of this Transition() returned by the 
        makeDict() method.
        
        @return: The comparison
        @rtype: bool
        
        '''
        
        try:        
            if self.makeDict() == other.makeDict():
                return True
            else:
                return False
        except AttributeError:
            return False
                


    def __ne__(self,other):
        
        '''
        Compare two transitions and return true if not equal.
        
        The condition is the dictionary of this Transition() returned by the 
        makeDict() method.
        
        @return: The negative comparison
        @rtype: bool
        
        '''
        
        try:
            if self.makeDict() != other.makeDict():
                return True
            else:
                return False
        except AttributeError:
            return True


 
    def __hash__(self):
        
        '''
        Return a hash number based on the string of the transition, but make 
        sure that every comparison includes the isTransition method of the 
        trans.
        
        @return: The hash number:
        @rtype: int
        
        '''
        
        return hash(str(self.makeDict()))



    def getInputString(self):
         
         '''
         Return a string giving the CC input line for this transition.
         
         This includes N_QUAD and has the shorthand naming convention of the 
         molecule as opposed to the str() method.
         
         @return: the input line for this transition
         @rtype: string
         
         '''
         
         return 'TRANSITION=%s %i %i %i %i %i %i %i %i %s %.2f %i' \
                %(self.molecule.molecule,self.vup,self.jup,self.kaup,\
                  self.kcup,self.vlow,self.jlow,self.kalow,self.kclow,\
                  self.telescope,self.offset,self.n_quad)
          

    
    def getLineSpec(self):
        
        '''
        Make a string that suits telescope.spec inputfile.
        
        @return: The Line spec string
        @rtype: string
        
        '''
        
        return 'LINE_SPEC=%s %i %i %i %i %i %i %i %i %.2f %.2f ! %s'\
               %(self.molecule.molecule_full,self.vup,self.jup,self.kaup,\
                 self.kcup,self.vlow,self.jlow,self.kalow,self.kclow,\
                self.getBeamwidth(),self.getEfficiency(),\
                self.molecule.molecule)



    def getBeamwidth(self):
        
        '''
        Calculate the beamwidth specific for the telescope.
        
        @return: The beamwidth
        @rtype: float
        
        '''
        
        #- get telescope diameter in cm
        if 'PACS' in self.telescope.upper():
            wav = array([55.,68,73,75,84,94,110,136,145,150,168,187])/10000.
            beam = array([8.4875,8.19,8.19,8.4525,8.2875,8.45,9.0625,9.6875,\
                          9.96,10.5425,11.0125,11.96])
            interp = interp1d(wav,beam)
            try:
                return interp(self.wavelength)
            except ValueError:
                print 'WARNING! The wavelength of %s falls '%str(self) +\
                      'outside of the interpolation range when determining '+\
                      'the beamwidth. Extrapolating linearly...'
                if self.wavelength < wav[0]:
                    return Interpol.linInterpol(wav[:2],beam[:2],\
                                                self.wavelength)
                else:
                    return Interpol.linInterpol(wav[-2:],beam[-2:],\
                                                self.wavelength)
        filename = os.path.join(os.path.expanduser('~'),'GASTRoNOoM','src',\
                                'data',self.telescope+'.spec')
        telescope_diameter = [float(line.split('=')[1][0:line.split('=')[1]\
                                    .index('!')].strip())
                              for line in DataIO.readFile(filename)
                              if line.find('TELESCOPE_DIAM') == 0][0] * 100.
        
        #- 1.22 is diffraction limited specification, 
        #- last factor is conversion to arcseconds
        return 1.22*self.wavelength/telescope_diameter*60.*60.*360./(2.*pi)  
        


    def getEfficiency(self):
        
        '''
        Calculate telescope beam efficiency. 
        
        Telescope specific!
        
        This beam efficiency is included in the .spec files for GASTRoNOoM.
        
        This number however is not used in any calculations of the line profile 
        and is included here for reference only. 
        
        The numbers currently are correct only for HIFI.
        
        @return: The beam efficiency
        @rtype: float
        
        '''
        
        if self.telescope.find('PACS') > -1 \
                or self.telescope.find('SPIRE') > -1:
            #- some random number, it is NOT relevant for PACS or SPIRE...
            return 0.60                 
        if self.telescope.find('HIFI') > -1:
            if self.frequency > 1116.2e9 and self.frequency < 1400.e9: 
                #- band 5a and 5b
                eff_mb0 = 0.66
            else:
                eff_mb0 = 0.76
            eff_f = 0.96
            sigma = 3.8e-4  #in cm
            eff_mb = eff_mb0 * exp(-1*(4*pi*sigma/self.wavelength)**2)
            return eff_mb/eff_f
        else:
            return 1.00



    def makeDict(self,in_progress=0):
        
        '''
        Return a dict with transition string, and other relevant parameters.
        
        @keyword in_progress: add an extra dict entry "IN_PROGRESS" if the 
                              transition is still being calculated on Vic.
                              
                              (default: 0)
        @type in_progress: bool
        
        @return: The transition dictionary including all relevant, defining 
                 information
        @rtype: dict()
        
        '''
        
        if int(in_progress):
            return dict([('TRANSITION',str(self).replace('TRANSITION=','')),\
                         ('N_QUAD',self.n_quad),\
                         ('USE_MASER_IN_SPHINX',self.use_maser_in_sphinx),\
                         ('IN_PROGRESS',1)])
        else:
            return dict([('TRANSITION',str(self).replace('TRANSITION=','')),\
                         ('N_QUAD',self.n_quad),\
                         ('USE_MASER_IN_SPHINX',self.use_maser_in_sphinx)])
 


    def makeSphinxFilename(self,number='*'):
        
        '''
        Return a string in the sphinx filename format.
         
        @keyword number: the number in the filename (sph*, sph1 or sph2, hence 
                         can be *, 1, 2)
                         
                         (default: '*')
        @type number: string
        
        @return: The sphinx filename for this transition
        @rtype: string
        
        '''
        
        try:
            number = str(int(number))
        except ValueError:
            number = str(number)
        quantum_dict = dict()
        if not self.molecule.spec_indices:
            for i,attr in enumerate(['vup','jup','vlow','jlow']):
                quantum_dict[i] = (attr,getattr(self,attr))
        elif self.molecule.spec_indices == 2:
            for i,attr in enumerate(['vup','Jup','Nup','vlow','jlow','Nlow']):
                quantum_dict[i] = (attr,getattr(self,attr.lower()))
        elif self.molecule.spec_indices == 3:
            for i,attr in enumerate(['vup','jup','vlow','jlow']):
                quantum_dict[i] = (attr,getattr(self,attr))            
        else:
            for i,attr in enumerate(['vup','jup','Kaup','Kcup',\
                                     'vlow','jlow','Kalow','Kclow']):
                quantum_dict[i] = (attr,getattr(self,attr.lower()))
        return '_'.join(['sph%s%s'%(number,self.getModelId()),\
                                    self.molecule.molecule] + \
                        ['%s%i'%(quantum_dict[k][0],quantum_dict[k][1])
                           for k in sorted(quantum_dict.keys())] + \
                        [self.telescope,'OFFSET%.2f.dat'%(self.offset)])
        


    def getFrequency(self):
        
        '''
        Get frequency of the transition from the radiat.dat files. 
        
        @return: frequency in Hz
        @rtype: float
        
        '''

        return self.frequency
        


    def getEnergyUpper(self):
         
        '''
        Return the energy level of the upper state of this transition.

        @return: energy level in cm^-1
        @rtype: float
    
        '''
        
        if self.molecule.radiat is None:
            print '%s_radiat.dat not found. Cannot find energy levels.'\
                  %self.molecule.molecule
            return
        energy = self.molecule.radiat.getEnergyLevels()
        return  float(energy[self.up_i-1])



    def getEnergyLower(self):

        '''
        Return the energy level of the lower state of this transition.

        @return: energy level in cm^-1
        @rtype: float
    
        '''
        
        if self.molecule.radiat is None:
            print '%s_radiat.dat not found. Cannot find energy levels.'\
                  %self.molecule.molecule
            return
        energy = self.molecule.radiat.getEnergyLevels()
        return  float(energy[self.low_i-1])



    def __setIndices(self):
         
        '''
        Set the index of this transition in the radiat file of GASTRoNOoM.
        
        The index from the indices file for lower and upper state are set.
        
        '''
        #- For 12C16O and 13C16O:
        #- indices = [i<60 and [i+1,0,i] or [i+1,1,i-60] for i in range(120)]
        #- As shown in above line, the first 60 (0-59) j's are associated with
        #- index (1-60) and v=0, the next 60 (60-119) j's are associated with 
        #- index (61-120) and v=1 

        if not self.molecule.spec_indices:
            self.up_i = self.jup + self.vup*self.molecule.ny_low + 1
            self.low_i = self.jlow + self.vlow*self.molecule.ny_low + 1
        else:
            indices = self.molecule.radiat_indices
            #- some molecules have only 2 or 3 relevant quantum numbers
            quantum_up = [q 
                            for i,q in enumerate([self.vup,self.jup,\
                                                    self.kaup,self.kcup]) 
                            if i<len(indices[0])-1]  
            quantum_low = [q 
                                for i,q in enumerate([self.vlow,self.jlow,\
                                                    self.kalow,self.kclow]) 
                                if i<len(indices[0])-1]
            #- Get index of the transition quantum numbers in the indices list
            #- If not present in list, ValueError is raised: probably caused 
            #- by using a linelist that doesn't include this transition.
            self.up_i  = indices[[i[1:] 
                                for i in indices].index(quantum_up)][0]
            self.low_i = indices[[i[1:] 
                                for i in indices].index(quantum_low)][0]
        self.radiat_trans = self.molecule.radiat.getTransInfo(low_i=self.low_i,\
                                                            up_i=self.up_i)
        if self.radiat_trans is False:
            raw_input('Something fishy is going on in Transition.py... '+\
                    'non-unique transition indices! Abort')
        self.frequency = float(self.radiat_trans['frequency'])
         

    def makeLabel(self):
        
        '''
        Return a short-hand label for this particular transition. 
        
        These labels can be used for plot line identifications for instance.
        
        If vibrational is not None, it always concerns a line list and is 
        included as well.
        
        @return: The transition label
        @rtype: string
        
        '''
        
        if self.vibrational:
            if not self.molecule.spec_indices:
                return '%s: %i,%i - %i,%i' \
                       %(self.vibrational,self.vup,self.jup,self.vlow,\
                         self.jlow)
            elif self.molecule.spec_indices == 2:
                return '%s: %i,%i$_{%i}$ - %i,%i$_{%i}$'\
                       %(self.vibrational,self.vup,self.jup,self.nup,\
                         self.vlow,self.jlow,self.nlow)
            elif self.molecule.spec_indices == 3:
                return '%s: %i$_{%i}$ - %i$_{%i}$' \
                       %(self.vibrational,self.jup,self.nup,self.jlow,\
                         self.nlow)
            else:
                return '%s: %i,%i$_{%i,%i}$ - %i,%i$_{%i,%i}$'\
                       %(self.vibrational,self.vup,self.jup,self.kaup,\
                         self.kcup,self.vlow,self.jlow,self.kalow,self.kclow)
        else:
            if not self.molecule.spec_indices:
                if self.vup == 0 and self.vlow ==0:
                    return '%i - %i' %(self.jup,self.jlow)
                else:
                    return '%i,%i - %i,%i' \
                           %(self.vup,self.jup,self.vlow,self.jlow)
            elif self.molecule.spec_indices == 2 \
                    or self.molecule.spec_indices == 3:
                return '%i,%i$_{%i}$ - %i,%i$_{%i}$'\
                       %(self.vup,self.jup,self.nup,self.vlow,self.jlow,\
                         self.nlow)
            else:
                return '%i,%i$_{%i,%i}$ - %i,%i$_{%i,%i}$'\
                       %(self.vup,self.jup,self.kaup,self.kcup,\
                         self.vlow,self.jlow,self.kalow,self.kclow)
            


    def setModelId(self,model_id):
        
        '''
        Set a model_id for the transition, identifying the model for SPHINX! 
        
        May or may not be equal to the molecule's id, depending on the input 
        parameters.
        
        @param model_id: The model id
        @type model_id: string
        
        '''
        
        self.__model_id = model_id
        


    def getModelId(self):
        
        '''
        Return the model_id associated with this transition. 
        
        None if not yet set.
        
        Empty string if the model calculation failed.
        
        @return: The model id of this transition
        @rtype: string
        
        '''
        
        return self.__model_id
        

    
    def isMolecule(self):
        
        '''
        Is this a Molecule() object?
        
        @return: Molecule()?
        @rtype: bool
        
        '''
        
        return False



    def isTransition(self):
        
        '''
        Is this a Transition() object?
        
        @return: Transition()?
        @rtype: bool
        
        '''
        
        return True
    


    def isDone(self):
        
        '''
        Return True if successfully calculated by sphinx, False otherwise.
        
        @return: Finished calculation?
        @rtype: bool
        
        '''
        
        return self.__model_id
        
        
    
    def setVexp(self,vexp):
        
        """
        Set the gas terminal velocity in this object. 
        
        @param vexp: The gas terminal velocity.
        @type vexp: float
        
        """
        
        if self.vexp is None:
            self.vexp = float(vexp)
        
    
    
    def readSphinx(self):
         
        '''
        Read the sphinx output if the model id is not None or ''.
        
        '''
         
        if self.sphinx is None and self.getModelId() <> None \
                and self.getModelId() != '':
            filename = os.path.join(os.path.expanduser('~'),'GASTRoNOoM',\
                                    self.path_gastronoom,'models',\
                                    self.getModelId(),\
                                    self.makeSphinxFilename())
            self.sphinx = SphinxReader.SphinxReader(filename)
     
     
     
    def addDatafile(self,datafile):
        
        '''
        Add a datafile name/multiple filenames for this transition. 
        
        @param datafile: the full filename, or multiple filenames
        @type datafile: string/list
        
        '''
        
        if type(datafile) is types.StringType:
            if self.datafiles is None:
                self.datafiles = [datafile]
            else: 
                self.datafiles.append(datafile)
        else:
            if self.datafiles is None:
                self.datafiles = datafile
            else: 
                self.datafiles.extend(datafile)
            
            

    def readData(self,vlsr):
         
        '''
        Read the datafiles associated with this transition if available.
         
        @param vlsr: The stellar velocity with respect to the local standard
                     of rest. Needed for fits files, in which no velocity 
                     information is given.
        @type vlsr: float
        
        '''
         
        if self.lpdata is None:
            self.lpdata = []
            if self.datafiles <> None:
                for df in self.datafiles:
                    if df[-5:] == '.fits':
                        lprof = FitsReader.FitsReader(df,vlsr)
                    else:
                        lprof = TxtReader.TxtReader(df,vlsr)
                    self.lpdata.append(lprof)
                    
    
    
    def setData(self,trans):
        
        """
        Set data equal to the data in a different Transition object, but for 
        the same transition. Does no erase data if they have already been set 
        in this object. 
        
        A check is ran to see if the transition in both objects really is the 
        same. Sphinx model id may differ! 
        
        Avoids too much overhead when reading data from files. 
        
        @param trans: The other Transition() object, assumes the transition 
                      is the same, but possibly different sphinx models.
        @type trans: Transition()        
        
        """
        
        if self.lpdata is None and self == trans: 
            self.lpdata = trans.lpdata
                
        
    
    def getBestVlsr(self,vlsr=None):
        
        """ 
        If self.best_vlsr is None, the best source velocity will be guessed by
        comparing chi^2 values between different values for the source velocity
        
        May be different from input vqlue vlsr, the original expected 
        source velocity!
        
        Based on the first dataset in self.lpdata. Note that multiple datasets
        might be included, but the scaling will be done for only the first one. 
        Since different datasets are for the same telescope, the same line
        and (usually) the same conditions, the source velocity is not expected
        to be different for the different datasets anyway. 
        
        Method will attempt to call self.readData and readSphinx if either are 
        not available. If data are still not available, the initial guess is 
        returned. If data are available, but sphinx isn't, vlsr from the fits
        files is returned, and the initial guess is returned in case of txt 
        files.
                
        @keyword vlsr: The stellar velocity with respect to the local standard
                       of rest. Needed for fits files, in which no velocity 
                       information is given. If None, no vlsr is needed. Data \
                       are already read. Will crash if that is not the case!
                       
                       (default: None)
        @type vlsr: float
        
        @return: the best guess vlsr, or the initial guess if no sphinx or data
                 are available [will return vlsr included in fitsfiles if 
                 available].
        @rtype: float
        
        """
        
        #- check if vlsr was already calculated
        if self.best_vlsr <> None:
            return self.best_vlsr
        #- attempt to read data
        self.readData(vlsr)
        #- if no data available, return initial guess
        if not self.lpdata:
            return vlsr
        #- get vlsr again, in case a fitsfile included a better guess
        vlsr = self.lpdata[0].getVlsr()
        #- check if sphinx is finished, if not return vlsr from data container
        self.readSphinx()
        if not self.sphinx: 
            return vlsr
        
        #- get all the profiles and noise values
        if self.vexp is None:
            print 'WARNING! Cannot calculate best v_lsr for %s'%str(self) + \
                  ' because the terminal gas velocity is not set.'
            return vlsr
        noise = self.lpdata[0].getNoise(self.vexp)
        dvel = self.lpdata[0].getVelocity()
        dtmb = self.lpdata[0].getFlux()
        mvel = self.sphinx.getVelocity()
        mtmb = self.sphinx.getLPTmb()
        
        #- make range of vlsr around the central value to find the best match
        #- using vexp as a range indicator, so we never fall out of the 
        #- interpolator range. Note that mvel is centered around zero.
        range_in_vlsr = linspace(vlsr-0.5*self.vexp,vlsr+0.5*self.vexp,31)
        #- interpolate the data fluxes 
        interpolator = interp1d(dvel,dtmb)
        #- use the new model velocity grids as inputs, and see what dtmb is
        dtmb_interp = [interpolator(mvel+vlsri) for vlsri in range_in_vlsr]
        #- Calculate the chi squared for every interpolated data tmb
        chisquared = [calcChiSquared(data=dtmbi[dtmbi>=-noise],model=mtmb[dtmbi>=-noise],noise=noise)
                      for dtmbi in dtmb_interp]
        #- Get the minimum chi squared and set the best_vlsr
        self.chi2_best_vlsr = min(chisquared)
        self.best_vlsr = range_in_vlsr[argmin(chisquared)]
        self.dtmb_best_vlsr = dtmb_interp[argmin(chisquared)]
        
        print "Best V_lsr: %f km/s, "%self.best_vlsr + \
              "original V_lsr: %f km/s for transition %s, %s."\
              %(vlsr,str(self),self.getModelId())
        
        return self.best_vlsr
        
    
    
    def getIntTmbSphinx(self):
        
        """
        Calculate the integrated Tmb of the sphinx line profile.
        
        Returns None if no sphinx profile is available yet!

        @return: The integrated model profile Tmb
        @rtype: float
        
        """
        
        if self.sphinx is None:
            self.readSphinx()
        if self.sphinx is None:
            return
        mvel = self.sphinx.getVelocity()
        mtmb = self.sphinx.getLPTmb()
        return trapz(x=mvel,y=mtmb)
    
    
    
    def getPeakTmbSphinx(self):
    
        """
        Get the peak Tmb of the sphinx line profile. 
        
        Returns None if no sphinx profile is available yet.
        
        Is equal to the mean of the 5 points around the center of the profile.
        
        @return: The peak Tmb of the sphinx line profile
        @rtype: float        
        
        """
        
        if self.sphinx is None:
            self.readSphinx()
        if self.sphinx is None:
            return
        mtmb = self.sphinx.getLPTmb()
        imid = len(mtmb)/2
        return mean(mtmb[imid-2:imid+3])
         
        
        
    
    def getIntTmbData(self,vlsr=None):
        
        """
        Calculate the integrated Tmb of the data line profile.
        
        Note that only the first of data profiles is used for this, if there 
        are multiple profiles available for this transition. (i.e. multiple
        observations of the same transition with the same telescope)
        
        Makes use of the interpolated line profile onto the sphinx velocity 
        grid for the best vlsr. This avoids taking into account too much 
        possible outliers in noisy spectra. Run getBestVlsr() first!
        
        Returns None if no sphinx or data are available. Both are needed!
        
        @keyword vlsr: The stellar velocity with respect to the local standard
                       of rest. Needed for fits files, in which no velocity 
                       information is given. If None, no vlsr is needed. Data \
                       are already read. Will crash if that is not the case!
                       
                       (default: None)
        @type vlsr: float
        
        @return: The integrated data Tmb
        @rtype: float
        
        """
        
        if self.best_vlsr is None:
            self.getBestVlsr(vlsr)
        if self.best_vlsr is None:
            return
        mvel = self.sphinx.getVelocity()
        return trapz(x=mvel,y=self.dtmb_best_vlsr)
        
        
    
    def getPeakTmbData(self,vlsr=None):
    
        """
        Get the peak Tmb of the data line profile. 
        
        Returns None if no sphinx profile or data are available yet.
        
        Makes use of the interpolated line profile onto the sphinx velocity 
        grid for the best vlsr. This avoids taking into account too much 
        possible outliers in noisy spectra. Run getBestVlsr() first!
        
        Is equal to the mean of the 5 points in the data profile around the 
        center of the sphinx profile (ie in the same velocity bin as 
        getPeakTmbSphinx).

        @keyword vlsr: The stellar velocity with respect to the local standard
                       of rest. Needed for fits files, in which no velocity 
                       information is given. If None, no vlsr is needed. Data \
                       are already read. Will crash if that is not the case!
                       
                       (default: None)
        @type vlsr: float

        @return: The peak Tmb of the sphinx line profile
        @rtype: float        
        
        """

        if self.best_vlsr is None:
            self.getBestVlsr(vlsr)
        if self.best_vlsr is None:
            return None
        #- Same velocity range as peak tmb of sphinx. Same velocity grid, so
        #- mid index can be determined as follows
        imid = len(self.dtmb_best_vlsr)/2
        return mean(self.dtmb_best_vlsr[imid-2:imid+3])
        
    
    
    def getLoglikelihood(self,vlsr=None):
        
        """
        Calculate the loglikelihood of comparison between sphinx and dataset.
        
        Gives a measure for the goodness of the fit of the SHAPE of the 
        profiles.
        
        Done only for the first dataset! Makes use of the interpolated line 
        profile onto the sphinx velocity grid for the best vlsr.
        
        Returns None if sphinx or data profile are not available. 
        
        Rescales the sphinx profile according to the difference in integrated
        Tmb between dataset and sphinx profile.

        @keyword vlsr: The stellar velocity with respect to the local standard
                       of rest. Needed for fits files, in which no velocity 
                       information is given. If None, no vlsr is needed. Data \
                       are already read. Will crash if that is not the case!
                       
                       (default: None)
        @type vlsr: float

        @return: The loglikelihood
        @rtype: float
        
        """
        
        if self.best_vlsr is None:
            self.getBestVlsr(vlsr)
        if self.best_vlsr is None:
            return None
        shift_factor = self.getIntTmbData()/self.getIntTmbSphinx()
        mtmb_scaled = self.sphinx.getLPTmb()*shift_factor
        noise = self.lpdata[0].getNoise()
        return calcLoglikelihood(data=self.dtmb_best_vlsr,model=mtmb_scaled,\
                                 noise=noise)