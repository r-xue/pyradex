from __future__ import print_function
import subprocess
import tempfile
import astropy.io.ascii 
import astropy.table
import numpy as np
import warnings
import astropy.units as u
from collections import defaultdict
import itertools
import os
try:
    from astropy import units as u
    from astropy import constants
except ImportError:
    u = False

__all__ = ['pyradex','write_input','parse_outfile', 'call_radex']


# silly tool needed for fortran misrepresentation of strings
# http://stackoverflow.com/questions/434287/what-is-the-most-pythonic-way-to-iterate-over-a-list-in-chunks
def grouper(iterable, n, fillvalue=None):
    args = [iter(iterable)] * n
    return itertools.izip_longest(*args, fillvalue=fillvalue)
        

def pyradex(executable='radex', minfreq=100, maxfreq=130,
            collider_densities={'H2':1}, debug=False, delete_tempfile=True,
            **kwargs):
    """
    Get the radex results for a set of input parameters


    Parameters
    ----------
    executable : str
        Full path to the RADEX executable
    minfreq : float
        Lowest frequency line to store, in GHz
        (note: any astropy.unit spectroscopic unit is also allowed)
    maxfreq : float
        Highest frequency line to store
    collider_densities : dict
        Collider names and their number densities
        If the molecule specified has both o-H2 and p-H2, you will get a
        WARNING if you specify 'H2'
        An ortho/para example:
        collider_densities = {'oH2':900, 'pH2':1000} 
        which will yield H2 = 1000

    See write_input for additional parameters

    Returns
    -------
    An astropy table containing the RADEX returns

    .. WARNING:: If RADEX spits out *******, it will be replaced with -999
    """

    infile,outfile = write_input(minfreq=minfreq, maxfreq=maxfreq,
            delete_tempfile=delete_tempfile,
            collider_densities=collider_densities, **kwargs)

    logfile = call_radex(executable, infile.name, debug=debug,
            delete_tempfile=delete_tempfile)

    check_logfile(logfile.name)

    data = parse_outfile(outfile.name)

    if debug:
        with open(infile.name,'r') as inf:
            print("Input:")
            print(inf.read())
        with open(outfile.name,'r') as out:
            print("Output:")
            print(out.read())

    infile.close()
    outfile.close()
    logfile.close()

    return data

def check_logfile(logfilename):
    with open(logfilename,'r') as f:
        if "Warning: Assuming thermal o/p ratio" in f.read():
            warnings.warn("Assumed thermal o/p ratio since only H2 was given but collider file has o- and p- H2")

def write_input(temperature=10, column=1e12, collider_densities={'H2':1},
        bw=0.01, tbg=2.73, species='co', velocity_gradient=1.0, minfreq=1,
        maxfreq=10, delete_tempfile=True):
    """
    Write radex.inp file parameters

    Parameters
    ----------
    temperature : float
        Kinetic temperature (K)
    collider_densities : dict
        Collider names and their number densities
    column : float
        column density of the molecule
    species : str
        Name of the molecule (specifically, the prefix for the file name, e.g.
        for "co.dat", species='co').  Case sensitive!
    tbg : float
        Temperature of the background radiation (e.g. CMB)
    velocity_gradient : float
        Velocity gradient per pc in km/s
    """

    if hasattr(minfreq, 'unit'):
        minfreq = minfreq.to('GHz',u.spectral()).value
    if hasattr(maxfreq, 'unit'):
        maxfreq = maxfreq.to('GHz',u.spectral()).value

    infile = tempfile.NamedTemporaryFile(mode='w', delete=delete_tempfile)
    outfile = tempfile.NamedTemporaryFile(mode='w', delete=delete_tempfile)
    infile.write(species+'.dat\n')
    infile.write(outfile.name+'\n')
    infile.write(str(minfreq)+' '+str(maxfreq)+'\n')
    infile.write(str(temperature)+'\n')

    # RADEX doesn't allow densities < 1e-3
    for k in collider_densities.keys():
        if collider_densities[k] < 1e-3:
            collider_densities.pop(k)

    infile.write('%s\n' % len(collider_densities))
    for name,dens in collider_densities.iteritems():
        infile.write('%s\n' % name)
        infile.write(str(dens)+'\n')
    infile.write(str(tbg)+'\n')
    infile.write(str(column)+'\n')
    infile.write(str(velocity_gradient)+'\n')
    # end the input file
    infile.write('0\n')
    infile.flush()
    return infile,outfile

def call_radex(executable, inpfilename, debug=False, delete_tempfile=True):

    logfile = tempfile.NamedTemporaryFile(mode='w', delete=delete_tempfile)
    cmd = '{radex} < {inpfile} > {logfile}'.format(
        radex=executable,
        inpfile=inpfilename,
        logfile=logfile.name)
    if debug:
        print("Command:",cmd)

    result = subprocess.call(cmd,
        shell=True)
    if result != 0:
        print("RADEX returned error code %i" % result)
        with open(logfile.name,'r') as f:
            print(f.read())

    return logfile


header_names = ['J_up','J_low','E_UP','FREQ', 'WAVE', 'T_EX', 'TAU', 'T_R', 'POP_UP', 'POP_LOW', 'FLUX_Kkms',   'FLUX_Inu']
header_units = [None,       None, u.K,   u.GHz,  u.um,   u.K,    None,  u.K,   None,     None,     u.K*u.km/u.s, u.erg/u.cm**2/u.s]
dtypes       = [str,   str,    float, float,  float,  float,  float, float,  float,    float,     float,         float]

def parse_outfile(filename):
    with open(filename,'r') as f:
        alllines = f.readlines()
        header = {L.split(":")[0][2:].strip():L.split(":")[1].strip()
                for L in alllines
                if L[0]=='*'}
        lines = [L.replace("--","  ") for L in alllines 
                if (L[0] != '*' 
                    and 'iterat' not in L 
                    and 'GHz' not in L 
                    and 'TAU' not in L)]
    data_list = [[x if '*' not in x else '-999' for x in L.split()] for L in lines]
    if len(data_list) == 0:
        raise ValueError("No lines included?")
    data_in_columns = map(list,zip(*data_list))
    columns = [astropy.table.Column(data=C, name=name.lower(), units=units, dtype=dtype) 
            for C,name,units,dtype in zip(data_in_columns, header_names, header_units, dtypes)]
    data = astropy.table.Table(columns, meta=header)
    return data

class Radex(object):

    def __call__(self, **kwargs):
        # reset the parameters appropriately
        self.__init__(**kwargs)
        self.run_radex()
        return self.get_table()

    def __init__(self,
                 collider_densities={'h2':1000},
                 temperature=30,
                 species='co',
                 column=1e13,
                 minfreq=100,
                 maxfreq=400,
                 tbackground=2.7315,
                 deltav=1.0,
                 length=3.085677581467192e+18,
                 abundance=None,
                 datapath='.',
                 method='lvg',
                 outfile='radex.out',
                 logfile='radex.log',
                 debug=False,
                 ):
        """
        Direct wrapper of the radex FORTRAN code

        Parameters
        ----------
        collider_densities: dict
            Dictionary giving the volume densities of the collider(s) in units of
            cm^-3.  Valid entries are h2,oh2,ph2,e,He,H,H+.  The keys are
            case-insensitive.
        temperature: float
            Local gas temperature in K
        species: str
            A string specifying a valid chemical species.  This is used to look
            up the specified molecule
        column: float
            The column density of the molecule of interest within the specified
            line width.  If the column is specified, the abundance is equal to
            (column/(dv*total density*length)).
        abundance: float
            The molecule's abundance relative to the total collider density in
            each velocity bin, i.e. column = abundance * density * length * dv.
            If both abundance and column are specified, abundance is ignored.
        minfreq: float
        maxfreq: float
            Minimum and maximum frequency to include in output
        tbackground: float
            Background radiation temperature (e.g., CMB)
        deltav: float
            The FWHM line width (really, the single-zone velocity width to
            scale the column density by: this is most sensibly interpreted as a
            velocity gradient (dv/length))
        length: float
            For abundance calculations, the line-of-sight size scale to
            associate with a velocity bin.  Typically, assume 1 km/s/pc,
            and thus set deltav=1, length=3.08e18
        datapath: str
            Path to the molecular data files
        outfile: str
            Output file name
        logfile: str
            Log file name
        method: 'lvg','sphere','slab'
            Which escape probability method to use
        """
        from pyradex.radex import radex
        self.radex = radex

        self.length = length

        self.density = collider_densities

        self.datapath = datapath
        self.molpath = os.path.join(datapath,species+'.dat')
        self.outfile = outfile
        self.logfile = logfile
        self.method = method

        self.deltav = deltav
        self.minfreq = minfreq
        self.maxfreq = maxfreq
        self._set_parameters()

        if column:
            self.column = column
        elif abundance:
            self.abundance = abundance
        else:
            raise ValueError("Must specify column or abundance.")

        self.temperature = temperature
        self.tbg = tbackground


        self.debug = debug

    def _set_parameters(self):

        #self.radex.cphys.cdmol = self.column
        #self.radex.cphys.tkin = self.temperature
        if u:
            self.radex.cphys.deltav = self.deltav.to(u.cm/u.s).value
        else:
            self.radex.cphys.deltav = self.deltav*1e5

        self.radex.freq.fmin = self.minfreq
        self.radex.freq.fmax = self.maxfreq

        self.miniter = 10
        self.maxiter = 200

    @property
    def density(self):
        d = {'H2':self.radex.cphys.density[0],
             'oH2':self.radex.cphys.density[1],
             'pH2':self.radex.cphys.density[2],
             'e':self.radex.cphys.density[3],
             'H':self.radex.cphys.density[4],
             'He':self.radex.cphys.density[5],
             'H+':self.radex.cphys.density[6]}
        if u:
            for k in d:
                d[k] = d[k] * u.cm**-3
        return d

    @density.setter
    def density(self, collider_density):
        collider_densities = defaultdict(lambda: 0)
        for k in collider_density:
            collider_densities[k.upper()] = collider_density[k]
        self.radex.cphys.density[0] = collider_densities['H2']
        self.radex.cphys.density[1] = collider_densities['OH2']
        self.radex.cphys.density[2] = collider_densities['PH2']
        self.radex.cphys.density[3] = collider_densities['E']
        self.radex.cphys.density[4] = collider_densities['H']
        self.radex.cphys.density[5] = collider_densities['HE']
        self.radex.cphys.density[6] = collider_densities['H+']
        self.radex.cphys.totdens = self.radex.cphys.density.sum()
    
    @property
    def totaldensity(self):
        if u:
            return self.radex.cphys.totdens * u.cm**-3
        else:
            return self.radex.cphys.totdens

    @property
    def molpath(self):
        return self.radex.impex.molfile

    @molpath.setter
    def molpath(self, molfile):
        self.radex.impex.molfile[:len(self.molpath)] = molfile

    @property
    def outfile(self):
        return self.radex.impex.outfile

    @outfile.setter
    def outfile(self, outfile):
        self.radex.impex.outfile[:len(self.outfile)] = outfile

    @property
    def logfile(self):
        return self.radex.setup.logfile

    @logfile.setter
    def logfile(self, logfile):
        self.radex.setup.logfile[:len(self.logfile)] = logfile

    @property
    def datapath(self):
        return self.radex.setup.radat

    @datapath.setter
    def datapath(self, radat):
        # self.radex data path not needed if molecule given as full path
        self.radex.setup.radat[:len(self.datapath)] = radat


    @property
    def method(self):
        return self.radex.setup.method

    @method.setter
    def method(self, method):
        mdict = {'lvg':2,'sphere':1,'slab':3}
        if method not in mdict:
            raise ValueError("Invalid method, must be one of "+",".join(mdict))
        self.radex.setup.method = mdict[method]
        

    @property
    def level_population(self):
        return self.radex.collie.xpop

    @property
    def tex(self):
        if u:
            return self.radex.radi.tex * u.K
        else:
            return self.radex.radi.tex

    @property
    def tau(self):
        return self.radex.radi.taul

    @property
    def frequency(self):
        if u:
            return self.radex.radi.spfreq * u.GHz
        else:
            return self.radex.radi.spfreq

    @property
    def temperature(self):
        if u:
            return self.radex.cphys.tkin*u.K
        else:
            return self.radex.cphys.tkin

    @temperature.setter
    def temperature(self, tkin):
        if tkin <= 0 or tkin > 1e4:
            raise ValueError('Must have kinetic temperature > 0 and < 10^4 K')
        self.radex.cphys.tkin = tkin
        # must re-read molecular file and re-interpolate to new temperature
        self.radex.readdata()

    @property
    def column(self):
        if u:
            return self.radex.cphys.cdmol * u.cm**-2
        else:
            return self.radex.cphys.cdmol

    @column.setter
    def column(self, col):
        if col < 1e5 or col > 1e25:
            raise ValueError("Extremely low or extremely high column.")
        self.radex.cphys.cdmol = col

    @property
    def column_per_bin(self):
        return self.column / self.deltav

    @column_per_bin.setter
    def total_column(self, cddv):
        if u:
            self.column = cddv * self.deltav.to(u.km/u.s).value
        else:
            self.column = cddv * self.deltav

    @property
    def abundance(self):
        abund = self.column / (self.totaldensity * self.length)
        if u:
            return abund.decompose().value
        else:
            return abund

    @abundance.setter
    def abundance(self, abund):
        col = abund * self.totaldensity * self.length
        if u:
            # need to divide the column per km/s by
            self.column = col.to(u.cm**-2).value
        else:
            self.column = col

    @property
    def deltav(self):
        return self._deltav

    @deltav.setter
    def deltav(self, dv):
        if u:
            self._deltav = dv * u.km/u.s
        else:
            self._deltav = dv

    @property
    def length(self):
        return self._length

    @length.setter
    def length(self, L):
        if u:
            self._length = L * u.cm
        else:
            self._length = L

    @property
    def debug(self):
        return self.radex.dbg.debug

    @debug.setter
    def debug(self, debug):
        self.radex.dbg.debug = debug

    @property
    def tbg(self):
        if u:
            return self.radex.cphys.tbg * u.K
        else:
            return self.radex.cphys.tbg

    @tbg.setter
    def tbg(self, tbg):
        #print("Set TBG=%f" % tbg)
        self.radex.cphys.tbg = tbg
        self.radex.backrad()

    def run_radex(self, silent=True, reuse_last=False, reload_molfile=True):
        """
        Run the iterative matrix solution using a python loop

        Parameters
        ----------
        silent: bool
            Print a message when iteration is done?
        reuse_last: bool
            If this is True, the matrix iterator will start at iteration 1
            rather than iteration 0, and it will therefore repopulate the rate
            matrix based on the radiative background alone.  In principle,
            setting this to True should result in a significantly faster
            convergence; in practice, it does not.
        reload_molfile: bool
            Re-read the molecular line file?  This is needed if the collision
            rates are different and have not been updated by, e.g., changing
            the temperature (which automatically runs the `readdata` function)
        """

        if reload_molfile or self.radex.collie.ctot.sum()==0:
            self.radex.readdata()

        #self.radex.backrad()
            
        self._iter_counter = 1 if reuse_last else 0
        
        converged = np.array(False)

        last = self.level_population.copy()

        while not converged:
            if self._iter_counter >= self.maxiter:
                if not silent:
                    print("Did not converge in %i iterations, stopping." % self.maxiter)
                break

            self.radex.matrix(self._iter_counter, converged)
            if np.abs(last-self.level_population).sum() < 1e-16 and self._iter_counter>self.miniter:
                if not silent:
                    print("Stopped changing after %i iterations" % self._iter_counter)
                break
            last = self.level_population.copy()
            self._iter_counter += 1

        if converged and not silent:
            print("Successfully converged after %i iterations" % self._iter_counter)

        return self._iter_counter

    @property
    def quantum_number(self):
        return np.array([("".join(x)).strip() for x in grouper(self.radex.quant.qnum.T.ravel().tolist(),6)])

    @property
    def upperlevelnumber(self):
        return self.radex.imolec.iupp

    @property
    def lowerlevelnumber(self):
        return self.radex.imolec.ilow

    @property
    def upperstateenergy(self):
        return self.radex.rmolec.eup

    @property
    def line_flux(self):
        return self.total_intensity - self.background_intensity

    @property
    def background_intensity(self):
        if u:
            return self.radex.radi.backi * u.erg * u.s**-1 * u.cm**-2 * u.Hz**-1 * u.sr**-1
        else:
            return self.radex.radi.backi

    @property
    def total_intensity(self):

        if u:
            thc = (2 * constants.h * constants.c).cgs / u.sr
            fk = (constants.h * constants.c / constants.k_B).cgs
            xnu = self.radex.radi.xnu * u.cm**-1
        else:
            thc = 3.9728913665386055e-16
            fk = 1.4387769599838154
            xnu = self.radex.radi.xnu

        ftau = np.exp(-self.tau)
        xt = xnu**3 # cm^-1 -> cm^-3
        bnutex = thc*xt/(np.exp(fk*xnu/self.tex)-1.0)
        toti = self.background_intensity*ftau+bnutex*(1.0-ftau)

        return toti

    def get_table(self, minfreq=None, maxfreq=None):
        T = astropy.table.Table()
        mask = self.tau > 0
        T.add_column(astropy.table.Column(name='Tex',data=self.tex[mask], unit='K'))
        T.add_column(astropy.table.Column(name='tau',data=self.tau[mask], unit=''))
        T.add_column(astropy.table.Column(name='frequency',data=self.frequency[mask], unit='GHz'))
        T.add_column(astropy.table.Column(name='upperstateenergy',data=self.upperstateenergy[mask], unit='K'))
        T.add_column(astropy.table.Column(name='upperlevel',data=self.quantum_number[self.upperlevelnumber[mask]], unit=''))
        T.add_column(astropy.table.Column(name='lowerlevel',data=self.quantum_number[self.lowerlevelnumber[mask]], unit=''))
        T.add_column(astropy.table.Column(name='upperlevelpop',data=self.level_population[self.upperlevelnumber[mask]], unit=''))
        T.add_column(astropy.table.Column(name='lowerlevelpop',data=self.level_population[self.lowerlevelnumber[mask]], unit=''))
        T.add_column(astropy.table.Column(name='flux',data=self.line_flux[mask]))

        return T
