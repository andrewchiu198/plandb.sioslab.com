import requests
import pandas
from StringIO import StringIO
import astropy.units as u
import astropy.constants as const
import EXOSIMS.PlanetPhysicalModel.Forecaster
from sqlalchemy import create_engine
import getpass,keyring
import numpy as np
import os
from scipy.interpolate import interp1d, interp2d, RectBivariateSpline
import sqlalchemy.types 
import re
import scipy.interpolate as interpolate

%pylab --no-import-all


#grab the data
query = """https://exoplanetarchive.ipac.caltech.edu/cgi-bin/nstedAPI/nph-nstedAPI?table=compositepars&select=*&format=csv"""
r = requests.get(query)
data = pandas.read_csv(StringIO(r.content))

query2 = """https://exoplanetarchive.ipac.caltech.edu/cgi-bin/nstedAPI/nph-nstedAPI?table=exoplanets&select=*&format=csv"""
r2 = requests.get(query2)
data2 = pandas.read_csv(StringIO(r2.content))

#strip leading 'f' on data colnames
colmap = {k:k[1:] if (k.startswith('fst_') | k.startswith('fpl_')) else k for k in data.keys()}
data = data.rename(columns=colmap)
#sma, eccen, metallicity cols were renamed so name them back for merge
data = data.rename(columns={'pl_smax':'pl_orbsmax',
                            'pl_smaxerr1':'pl_orbsmaxerr1',
                            'pl_smaxerr2':'pl_orbsmaxerr2',
                            'pl_smaxlim':'pl_orbsmaxlim',
                            'pl_smaxreflink':'pl_orbsmaxreflink',
                            'pl_eccen':'pl_orbeccen',
                            'pl_eccenerr1':'pl_orbeccenerr1',
                            'pl_eccenerr2':'pl_orbeccenerr2',
                            'pl_eccenlim':'pl_orbeccenlim',
                            'pl_eccenreflink':'pl_orbeccenreflink',
                            'st_met':'st_metfe', 
                            'st_meterr1':'st_metfeerr1', 
                            'st_meterr2':'st_metfeerr2',
                            'st_metreflink':'st_metfereflink',
                            'st_metlim':'st_metfelim', 
                            })

#sort by planet name 
data = data.sort_values(by=['pl_name']).reset_index(drop=True)
data2 = data2.sort_values(by=['pl_name']).reset_index(drop=True)

#merge data sets
data = data.combine_first(data2)


###############################
#some sanity checking
data3 = data.combine_first(data2)

ccols = np.array(list(set(data.keys()) & set(data2.keys())))
ncols = np.array(list(set(data2.keys()) - set(data.keys())))

#compare redundant cols
diffcs = []
diffinds = []
for c in ccols:
    tmp = (data[c].values == data2[c].values) | (data[c].isnull().values & data2[c].isnull().values)
    if not np.all( tmp ):
        diffcs.append(c)
        diffinds.append(np.where(~tmp)[0])

for c,inds in zip(diffcs,diffinds):
    print c
    tmp = data[c][inds].isnull().values & ~(data2[c][inds].isnull().values)
    assert np.all(data3[c][inds][tmp] == data2[c][inds][tmp])
###############################


## filter rows:
# we need:
# distance AND
# (sma OR (period AND stellar mass)) AND
# (radius OR mass (either true or m\sin(i)))
keep = ~np.isnan(data['st_dist'].values) & (~np.isnan(data['pl_orbsmax'].values) | \
        (~np.isnan(data['pl_orbper'].values) & ~np.isnan(data['st_mass'].values))) & \
       (~np.isnan(data['pl_bmassj'].values) | ~np.isnan(data['pl_radj'].values))
data = data[keep]
data = data.reset_index(drop=True)


##fill in missing smas from period & star mass
nosma = np.isnan(data['pl_orbsmax'].values)
p2sma = lambda mu,T: ((mu*T**2/(4*np.pi**2))**(1/3.)).to('AU')
GMs = const.G*(data['st_mass'][nosma].values*u.solMass) # units of solar mass
T = data['pl_orbper'][nosma].values*u.day
tmpsma = p2sma(GMs,T)
data['pl_orbsmax'][nosma] = tmpsma
data['pl_orbsmaxreflink'][nosma] = "Calculated from stellar mass and orbital period."

##update all WAs based on sma
WA = np.arctan((data['pl_orbsmax'].values*u.AU)/(data['st_dist'].values*u.pc)).to('mas')
data['pl_angsep'] = WA.value


###################################################################
#devel (skip)
#forecaster original
#S = np.array([0.2790,0.589,-0.044,0.881]) #orig coeffs
#C0 = np.log10(1.008)
#T = np.array([2.04,((0.414*u.M_jupiter).to(u.M_earth)).value,((0.0800*u.M_sun).to(u.M_earth)).value])
#C = np.hstack((C0, C0 + np.cumsum(-np.diff(S)*np.log10(T))))

#modify neptune and jupiter leg with new transition point at saturn mass and then flat leg past jupiter mass
S = np.array([0.2790,0,0,0,0.881])
C = np.array([np.log10(1.008), 0, 0, 0, 0])
T = np.array([2.04,95.16,(u.M_jupiter).to(u.M_earth),((0.0800*u.M_sun).to(u.M_earth)).value])

Rj = u.R_jupiter.to(u.R_earth)
Rs = 8.522 #saturn radius

S[1] = (np.log10(Rs) - (C[0] + np.log10(T[0])*S[0]))/(np.log10(T[1]) - np.log10(T[0]))
C[1] = np.log10(Rs) - np.log10(T[1])*S[1]

S[2] = (np.log10(Rj) - np.log10(Rs))/(np.log10(T[2]) - np.log10(T[1]))
C[2] = np.log10(Rj) - np.log10(T[2])*S[2]

C[3] = np.log10(Rj)

C[4] = np.log10(Rj) - np.log10(T[3])*S[4]

##forecaster sanity check:
m1 = np.array([1e-3,T[0]])
r1 = 10.**(C[0] + np.log10(m1)*S[0])

m2 = T[0:2]
r2 = 10.**(C[1] + np.log10(m2)*S[1])

m3 = T[1:3]
r3 = 10.**(C[2] + np.log10(m3)*S[2])

m4 = T[2:4]
r4 = 10.**(C[3] + np.log10(m4)*S[3])

m5 = np.array([T[3],1e6])
r5 = 10.**(C[4] + np.log10(m5)*S[4])

plt.figure()
plt.loglog(m1,r1)
plt.loglog(m2,r2)
plt.loglog(m3,r3)
plt.loglog(m4,r4)
plt.loglog(m5,r5)
plt.xlabel('Mass ($M_\oplus$)')
plt.ylabel('Radius ($R_\oplus$)')
##################################################################


#drop all other radius columns
data = data.drop(columns=['pl_rade',  'pl_radelim',  'pl_radserr2', 'pl_radeerr1', 'pl_rads', 'pl_radslim', 'pl_radeerr2', 'pl_radserr1']) 

#fill in radius based on mass
noR = ((data['pl_radreflink'] == '<a refstr="CALCULATED VALUE" href="/docs/composite_calc.html" target=_blank>Calculated Value</a>') |\
        data['pl_radj'].isnull()).values

m = ((data['pl_bmassj'][noR].values*u.M_jupiter).to(u.M_earth)).value

def RfromM(m):
    m = np.array(m,ndmin=1)
    R = np.zeros(m.shape)


    S = np.array([0.2790,0,0,0,0.881])
    C = np.array([np.log10(1.008), 0, 0, 0, 0])
    T = np.array([2.04,95.16,(u.M_jupiter).to(u.M_earth),((0.0800*u.M_sun).to(u.M_earth)).value])

    Rj = u.R_jupiter.to(u.R_earth)
    Rs = 8.522 #saturn radius

    S[1] = (np.log10(Rs) - (C[0] + np.log10(T[0])*S[0]))/(np.log10(T[1]) - np.log10(T[0]))
    C[1] = np.log10(Rs) - np.log10(T[1])*S[1]

    S[2] = (np.log10(Rj) - np.log10(Rs))/(np.log10(T[2]) - np.log10(T[1]))
    C[2] = np.log10(Rj) - np.log10(T[2])*S[2]

    C[3] = np.log10(Rj)

    C[4] = np.log10(Rj) - np.log10(T[3])*S[4]


    inds = np.digitize(m,np.hstack((0,T,np.inf)))
    for j in range(1,inds.max()+1):
        R[inds == j] = 10.**(C[j-1] + np.log10(m[inds == j])*S[j-1])

    return R

R = RfromM(m)

#create mod forecaster radius column
data = data.assign(pl_radj_forecastermod=data['pl_radj'].values)
data['pl_radj_forecastermod'][noR] = ((R*u.R_earth).to(u.R_jupiter)).value
     

## now the Fortney model
from EXOSIMS.PlanetPhysicalModel.FortneyMarleyCahoyMix1 import FortneyMarleyCahoyMix1
fortney = FortneyMarleyCahoyMix1()

ml10 = m <= 17
Rf = np.zeros(m.shape)
Rf[ml10] = fortney.R_ri(0.67,m[ml10])

mg10 = m > 17
tmpsmas = data['pl_orbsmax'][noR].values
tmpsmas = tmpsmas[mg10]
tmpsmas[tmpsmas < fortney.giant_pts2[:,1].min()] = fortney.giant_pts2[:,1].min()
tmpsmas[tmpsmas > fortney.giant_pts2[:,1].max()] = fortney.giant_pts2[:,1].max()

tmpmass = m[mg10]
tmpmass[tmpmass > fortney.giant_pts2[:,2].max()] = fortney.giant_pts2[:,2].max()

Rf[mg10] = interpolate.griddata(fortney.giant_pts2, fortney.giant_vals2,( np.array([10.]*np.where(mg10)[0].size), tmpsmas, tmpmass))

data = data.assign(pl_radj_fortney=data['pl_radj'].values)
data['pl_radj_fortney'][noR] = ((Rf*u.R_earth).to(u.R_jupiter)).value


#######
#quick fig for docs
plt.figure()
plt.plot(R,Rf,'.')
plt.plot([0,12],[0,12])
plt.xlim([0,12])
plt.ylim([0,12])
plt.xlabel('Modified Forecster Fit ($R_\oplus$)')
plt.ylabel('Fortney et al. (2007) Fit ($R_\oplus$)')

#######


##populate max WA based on available eccentricity data (otherwise maxWA = WA)
hase = ~np.isnan(data['pl_orbeccen'].values)
maxWA = WA[:]
maxWA[hase] = np.arctan((data['pl_orbsmax'][hase].values*(1 + data['pl_orbeccen'][hase].values)*u.AU)/(data['st_dist'][hase].values*u.pc)).to('mas')
data = data.assign(pl_maxangsep=maxWA.value)

#populate min WA based on eccentricity & inclination data (otherwise minWA = WA)
hasI =  ~np.isnan(data['pl_orbincl'].values)
s = data['pl_orbsmax'].values*u.AU
s[hase] *= (1 - data['pl_orbeccen'][hase].values)
s[hasI] *= np.cos(data['pl_orbincl'][hasI].values*u.deg)
s[~hasI] = 0
minWA = np.arctan(s/(data['st_dist'].values*u.pc)).to('mas')
data = data.assign(pl_minangsep=minWA.value)


#data.to_pickle('data_062818.pkl')

##############################################################################################################################
# grab photometry data 
#enginel = create_engine('sqlite:///' + os.path.join(os.getenv('HOME'),'Documents','AFTA-Coronagraph','ColorFun','AlbedoModels.db'))
enginel = create_engine('sqlite:///' + os.path.join(os.getenv('HOME'),'Documents','AFTA-Coronagraph','ColorFun','AlbedoModels_2015.db'))

# getting values
meta_alb = pandas.read_sql_table('header',enginel)
metallicities = meta_alb.metallicity.unique()
metallicities.sort()
betas = meta_alb.phase.unique()
betas.sort()
dists = meta_alb.distance.unique()
dists.sort()
clouds = meta_alb.cloud.unique()
clouds.sort()
cloudstr = clouds.astype(str)
for j in range(len(cloudstr)):
    cloudstr[j] = 'f'+cloudstr[j]
cloudstr[cloudstr == 'f0.0'] = 'NC'
cloudstr[cloudstr == 'f1.0'] = 'f1'
cloudstr[cloudstr == 'f3.0'] = 'f3'
cloudstr[cloudstr == 'f6.0'] = 'f6'

tmp = pandas.read_sql_table('g25_t150_m0.0_d0.5_NC_phang000',enginel)
wavelns = tmp.WAVELN.values

##################
#unnecessary if pulling all phot data
photdata550 = np.zeros((meta_alb.metallicity.unique().size,meta_alb.distance.unique().size, meta_alb.phase.unique().size))
for i,fe in enumerate(meta_alb.metallicity.unique()):
    basename = 'g25_t150_m'+str(fe)+'_d'
    print(basename)
    for j,d in enumerate(meta_alb.distance.unique()):
        for k,beta in enumerate(meta_alb.phase.unique()):
            name = basename+str(d)+'_NC_phang'+"%03d"%beta
            try:
                tmp = pandas.read_sql_table(name,enginel)
            except:
                photdata550[i,j,k] = np.nan
                continue
            ind = np.argmin(np.abs(tmp['WAVELN']-0.550))
            pval = tmp['GEOMALB'][ind]
            photdata550[i,j,k] = pval

photinterps = {}
for i,fe in enumerate(meta_alb.metallicity.unique()):
    photinterps[fe] = {}
    for j,d in enumerate(meta_alb.distance.unique()):
        photinterps[fe][d] = interp1d(betas[np.isfinite(photdata550[i,j,:])],photdata550[i,j,:][np.isfinite(photdata550[i,j,:])],kind='cubic')
#################

allphotdata = np.zeros((metallicities.size, dists.size, clouds.size, betas.size, wavelns.size))
for i,fe in enumerate(metallicities):
    basename = 'g25_t150_m'+str(fe)+'_d'
    for j,d in enumerate(dists):
        basename2 = basename+str(d)+'_'
        for k,cloud in enumerate(clouds):
            basename3 = basename2+cloudstr[k]+'_phang'
            print(basename3)
            for l,beta in enumerate(betas):
                name = basename3+"%03d"%beta
                try:
                    tmp = pandas.read_sql_table(name,enginel)
                except:
                    print("Missing: %s"%name)
                    allphotdata[i,j,k,l,:] = np.nan
                    continue
                pvals = tmp['GEOMALB'].values
                if len(tmp) != len(wavelns):
                    missing = list(set(wavelns) - set(tmp.WAVELN.values))
                    inds  = np.searchsorted(tmp['WAVELN'].values,missing)
                    pvals = np.insert(pvals,inds,np.nan)
                    assert np.isnan(pvals[wavelns==missing[0]])
                    print("Filled value: %s, %s"%(name,missing))
                allphotdata[i,j,k,l,:] = pvals



#patch individual nans
for i,fe in enumerate(metallicities):
    for j,d in enumerate(dists):
        for k,cloud in enumerate(clouds):
            for l,beta in enumerate(betas):
                nans = np.isnan(allphotdata[i,j,k,l,:])
                if np.any(nans) & ~np.all(nans):
                    tmp = interp1d(wavelns[~nans],allphotdata[i,j,k,l,~nans],kind='cubic')
                    allphotdata[i,j,k,l,nans] = tmp(wavelns[nans])


##np.savez('allphotdata',metallicities=metallicities,dists=dists,clouds=clouds,cloudstr=cloudstr,betas=betas,wavelns=wavelns,allphotdata=allphotdata)
#np.savez('allphotdata_2015',metallicities=metallicities,dists=dists,clouds=clouds,cloudstr=cloudstr,betas=betas,wavelns=wavelns,allphotdata=allphotdata)


#######
# visualization:
wind = np.argmin(np.abs(wavelns - 0.575))
dind = np.argmin(np.abs(dists - 1))

ls = ["-","--","-.",":","o-","s-","d-","h-"]

plt.figure()
for j in range(clouds.size):
    plt.plot(betas,allphotdata[0,dind,j,:,wind],ls[j],label=cloudstr[j])

plt.ylabel('$p\Phi(\\beta)$')
plt.xlabel('Phase (deg)')
plt.xlim([0,180])
plt.legend()

########
#restore photdata fromdisk
#tmp = np.load('allphotdata.npz')
tmp = np.load('allphotdata_2015.npz')
allphotdata = tmp['allphotdata']
clouds = tmp['clouds']
cloudstr = tmp['cloudstr']
wavelns = tmp['wavelns']
betas = tmp['betas']
dists = tmp['dists']
metallicities = tmp['metallicities']
#########


def makeninterp(vals):
    ii =  interp1d(vals,vals,kind='nearest',bounds_error=False,fill_value=(vals.min(),vals.max()))
    return ii

distinterp = makeninterp(dists)
betainterp = makeninterp(betas)
feinterp = makeninterp(metallicities)
cloudinterp = makeninterp(clouds)


photinterps2 = {}
for i,fe in enumerate(metallicities):
    photinterps2[fe] = {}
    for j,d in enumerate(dists):
        photinterps2[fe][d] = {}
        for k,cloud in enumerate(clouds):
            if np.any(np.isnan(allphotdata[i,j,k,:,:])):
                #remove whole rows of betas
                goodbetas = np.array(list(set(range(len(betas))) - set(np.unique(np.where(np.isnan(allphotdata[i,j,k,:,:]))[0]))))
                photinterps2[fe][d][cloud] = RectBivariateSpline(betas[goodbetas],wavelns,allphotdata[i,j,k,goodbetas,:])
                #photinterps2[fe][d][cloud] = interp2d(betas[goodbetas],wavelns,allphotdata[i,j,k,goodbetas,:].transpose(),kind='cubic')
            #photinterps2[fe][d][cloud] = interp2d(betas,wavelns,allphotdata[i,j,k,:,:].transpose(),kind='cubic')
            photinterps2[fe][d][cloud] = RectBivariateSpline(betas,wavelns,allphotdata[i,j,k,:,:])



##############################################################################################################################

#orbit info
from EXOSIMS.util.eccanom import eccanom
from EXOSIMS.util.deltaMag import deltaMag
import EXOSIMS.Prototypes.PlanetPhysicalModel
PPMod = EXOSIMS.Prototypes.PlanetPhysicalModel.PlanetPhysicalModel()
M = np.linspace(0,2*np.pi,100)
plannames = data['pl_name'].values

#wavelengths of interest
#lambdas = np.array([575, 635, 660, 706, 760, 825])
labmdas = [575,  660, 730, 760, 825]
bps = [10,18,18,18,10]

orbdata = None
#row = data.iloc[71] 
for j in range(len(plannames)):
    print(plannames[j])
    row = data.iloc[j] 

    a = row['pl_orbsmax']
    e = row['pl_orbeccen'] 
    if np.isnan(e): e = 0.0
    I = row['pl_orbincl']*np.pi/180.0
    if np.isnan(I): I = np.pi/2.0
    w = row['pl_orblper']*np.pi/180.0
    if np.isnan(w): w = 0.0
    E = eccanom(M, e)                      
    Rp = row['pl_radj']
    dist = row['st_dist']
    fe = row['st_metfe']
    if np.isnan(fe): fe = 0.0

    a1 = np.cos(w) 
    a2 = np.cos(I)*np.sin(w)
    a3 = np.sin(I)*np.sin(w)
    A = a*np.vstack((a1, a2, a3))

    b1 = -np.sqrt(1 - e**2)*np.sin(w)
    b2 = np.sqrt(1 - e**2)*np.cos(I)*np.cos(w)
    b3 = np.sqrt(1 - e**2)*np.sin(I)*np.cos(w)
    B = a*np.vstack((b1, b2, b3))
    r1 = np.cos(E) - e
    r2 = np.sin(E)

    r = (A*r1 + B*r2).T
    d = np.linalg.norm(r, axis=1)
    s = np.linalg.norm(r[:,0:2], axis=1)
    beta = np.arccos(r[:,2]/d)*u.rad

    WA = np.arctan((s*u.AU)/(dist*u.pc)).to('mas').value
    print(j,plannames[j],WA.min() - minWA[j].value, WA.max() - maxWA[j].value)

    outdict = {'Name': [plannames[j]]*len(M),
                'M': M,
                'r': d,
                's': s,
                'WA': WA,
                'beta': beta.to(u.deg).value}

    inds = np.argsort(beta)
    for c in clouds:
        for l in lambdas:
            pphi = photinterps2[float(feinterp(fe))][float(distinterp(a))][c](beta.to(u.deg).value[inds],float(l)/1000.)[np.argsort(inds)].flatten()
            pphi[np.isinf(pphi)] = np.nan
            outdict['pPhi_'+"%03dC_"%(c*100)+str(l)+"NM"] = pphi 
            dMag = deltaMag(1, Rp*u.R_jupiter, d*u.AU, pphi)
            dMag[np.isinf(dMag)] = np.nan
            outdict['dMag_'+"%03dC_"%(c*100)+str(l)+"NM"] = dMag

    #pphi = np.array([ photinterps[float(feinterp(fe))][float(distinterp(di))](bi) for di,bi in zip(d,beta.to(u.deg).value) ])
    #dMag = deltaMag(1, Rp*u.R_jupiter, d*u.AU, pphi)

    #phi = PPMod.calc_Phi(np.arccos(r[:,2]/d)*u.rad) 
    #dMag = deltaMag(0.5, Rp*u.R_jupiter, d*u.AU, phi)


    out = pandas.DataFrame(outdict)
    
    if orbdata is None:
        orbdata = out.copy()
    else:
        orbdata = orbdata.append(out)



##############################################################################################################################

minangsep = 100
maxangsep = 500

inds = np.where((data['pl_maxangsep'].values > minangsep) & (data['pl_minangsep'].values < maxangsep))[0]

WAbins0 = np.arange(minangsep,maxangsep+1,1)
WAbins = np.hstack((0, WAbins0, np.inf))
dMagbins0 = np.arange(0,26.1,0.1)
dMagbins = np.hstack((dMagbins0,np.inf))

WAc,dMagc = np.meshgrid(WAbins0[:-1]+np.diff(WAbins0)/2.0,dMagbins0[:-1]+np.diff(dMagbins0)/2.0)
WAc = WAc.T
dMagc = dMagc.T

WAinds = np.arange(WAbins0.size-1)
dMaginds = np.arange(dMagbins0.size-1)
WAinds,dMaginds = np.meshgrid(WAinds,dMaginds)
WAinds = WAinds.T
dMaginds = dMaginds.T

names = []
WAcs = []
dMagcs = []
iinds = []
jinds = []
hs = []
cs = []
goodinds = []
for j in inds:
    row = data.iloc[j] 
    print row['pl_name']
    
    amu = row['pl_orbsmax']
    astd = (row['pl_orbsmaxerr1'] - row['pl_orbsmaxerr2'])/2.
    if np.isnan(astd): astd = 0.01*amu
    gena = lambda n: np.clip(np.random.randn(n)*astd + amu,0,np.inf)

    emu = row['pl_orbeccen'] 
    if np.isnan(emu):
        gene = lambda n: 0.175/np.sqrt(np.pi/2.)*np.sqrt(-2.*np.log(1 - np.random.uniform(size=n)))
    else:
        estd = (row['pl_orbeccenerr1'] - row['pl_orbeccenerr2'])/2.
        if np.isnan(estd) or (estd == 0):
            estd = 0.01*emu
        gene = lambda n: np.clip(np.random.randn(n)*estd + emu,0,0.99)

    Imu = row['pl_orbincl']*np.pi/180.0
    if np.isnan(Imu):
        if row['pl_bmassprov'] == 'Msini':
            Icrit = np.arcsin( ((row['pl_bmassj']*u.M_jupiter).to(u.M_earth)).value/((0.0800*u.M_sun).to(u.M_earth)).value )
            Irange = [Icrit, np.pi - Icrit]
            C = 0.5*(np.cos(Irange[0])-np.cos(Irange[1]))
            genI = lambda n: np.arccos(np.cos(Irange[0]) - 2.*C*np.random.uniform(size=n))

        else:
            genI = lambda n: np.arccos(1 - 2.*np.random.uniform(size=n))
    else:
        Istd = (row['pl_orbinclerr1'] - row['pl_orbinclerr2'])/2.*np.pi/180.0
        if np.isnan(Istd) or (Istd == 0): 
            Istd = Imu*0.01
        genI = lambda n: np.random.randn(n)*Istd + Imu
    

    wbarmu = row['pl_orblper']*np.pi/180.0
    if np.isnan(wbarmu):
        genwbar = lambda n: np.random.uniform(size=n,low=0.0,high=2*np.pi)
    else:
        wbarstd = (row['pl_orblpererr1'] - row['pl_orblpererr2'])/2.*np.pi/180.0
        if np.isnan(wbarstd) or (wbarstd == 0): 
            wbarstd = wbarmu*0.01
        genwbar = lambda n: np.random.randn(n)*wbarstd + wbarmu

    fe = row['st_metfe']
    if np.isnan(fe): fe = 0.0


    n = int(1e6)
    c = 0.
    h = np.zeros((len(WAbins)-3, len(dMagbins)-2))
    k = 0.0

    cprev = 0.0
    pdiff = 1.0

    while (pdiff > 0.0001) | (k <3):
    #for blah in range(100):
        print("%d \t %5.5e \t %5.5e"%( k,pdiff,c))
        a = gena(n)
        e = gene(n)
        I = genI(n)
        O = np.random.uniform(size=n,low=0.0,high=2*np.pi)
        wbar = genwbar(n)
        w = O - wbar

        if (row['pl_radreflink'] == "Calculated via modified Forecaster disallowing radii > 1 R_J."):
            if row['pl_bmassprov'] == 'Msini':
                Mp = ((row['pl_bmassj']*u.M_jupiter).to(u.M_earth)).value
                Mp = Mp/np.sin(I)
            else:
                Mstd = (((row['pl_bmassjerr1'] - row['pl_bmassjerr2'])*u.M_jupiter).to(u.M_earth)).value
                if np.isnan(Mstd):
                    Mstd = ((row['pl_bmassj']*u.M_jupiter).to(u.M_earth)).value * 0.1
                Mp = np.random.randn(n)*Mstd + ((row['pl_bmassj']*u.M_jupiter).to(u.M_earth)).value

            R = (RfromM(Mp)*u.R_earth).to(u.R_jupiter).value
            R[R > 1.0] = 1.0
        else:
            Rmu = row['pl_radj']
            Rstd = (row['pl_radjerr1'] - row['pl_radjerr2'])/2.
            if np.isnan(Rstd): Rstd = Rmu*0.1
            R = np.random.randn(n)*Rstd + Rmu
        
        M0 = np.random.uniform(size=n,low=0.0,high=2*np.pi)
        E = eccanom(M0, e)                     
        
        a1 = np.cos(O)*np.cos(w) - np.sin(O)*np.cos(I)*np.sin(w)
        a2 = np.sin(O)*np.cos(w) + np.cos(O)*np.cos(I)*np.sin(w)
        a3 = np.sin(I)*np.sin(w)
        A = a*np.vstack((a1, a2, a3))
        b1 = -np.sqrt(1 - e**2)*(np.cos(O)*np.sin(w) + np.sin(O)*np.cos(I)*np.cos(w))
        b2 = np.sqrt(1 - e**2)*(-np.sin(O)*np.sin(w) + np.cos(O)*np.cos(I)*np.cos(w))
        b3 = np.sqrt(1 - e**2)*np.sin(I)*np.cos(w)
        B = a*np.vstack((b1, b2, b3))
        r1 = np.cos(E) - e
        r2 = np.sin(E)
        
        rvec = (A*r1 + B*r2).T
        rnorm = np.linalg.norm(rvec, axis=1)
        s = np.linalg.norm(rvec[:,0:2], axis=1)
        beta = np.arccos(rvec[:,2]/rnorm)*u.rad
        #phi = PPMod.calc_Phi(np.arccos(rvec[:,2]/rnorm)*u.rad)    # planet phase
        #dMag = deltaMag(0.5, R*u.R_jupiter, rnorm*u.AU, phi)     # delta magnitude
        pphi = photinterps[float(feinterp(fe))][float(distinterp(np.mean(rnorm)))](beta.to(u.deg).value)
        dMag = deltaMag(1, R*u.R_jupiter, rnorm*u.AU, pphi)

        WA = np.arctan((s*u.AU)/(row['st_dist']*u.pc)).to('mas').value # working angle

        h += np.histogram2d(WA,dMag,bins=(WAbins,dMagbins))[0][1:-1,0:-1]
        k += 1.0
        currc = float(len(np.where((WA >= minangsep) & (WA <= maxangsep) & (dMag <= 22.5))[0]))/n
        cprev = c
        if k == 1.0:
            c = currc
        else:
            c = ((k-1)*c + currc)/k
        if c == 0:
            pdiff = 1.0
        else:
            pdiff = np.abs(c - cprev)/c

        if (c == 0.0) & (k > 2):
            break

        if (c < 1e-5) & (k > 25):
            break

    if c != 0.0:
        h = h/float(n*k)
        names.append(np.array([row['pl_name']]*h.size))
        WAcs.append(WAc.flatten())
        dMagcs.append(dMagc.flatten())
        hs.append(h.flatten())
        iinds.append(WAinds.flatten())
        jinds.append(dMaginds.flatten())
        cs.append(c)
        goodinds.append(j)

    print("\n\n\n\n")

cs = np.array(cs)
goodinds = np.array(goodinds)


out2 = pandas.DataFrame({'Name': np.hstack(names),
                         'alpha': np.hstack(WAcs),
                         'dMag': np.hstack(dMagcs),
                         'H':    np.hstack(hs),
                         'iind': np.hstack(iinds),
                         'jind': np.hstack(jinds)
                         })
out2 = out2[out2['H'].values != 0.]
out2['H'] = np.log10(out2['H'].values)



minCWA = []
maxCWA = []
minCdMag = []
maxCdMag = []

for j in range(len(goodinds)):
    minCWA.append(np.floor(np.min(WAcs[j][hs[j] != 0])))
    maxCWA.append(np.ceil(np.max(WAcs[j][hs[j] != 0])))
    minCdMag.append(np.floor(np.min(dMagcs[j][hs[j] != 0])))
    maxCdMag.append(np.ceil(np.max(dMagcs[j][hs[j] != 0])))

###################################################################
#build alias table
from astroquery.simbad import Simbad

starnames = data['pl_hostname'].unique()

s = Simbad()
s.add_votable_fields('ids')
baseurl = "https://exoplanetarchive.ipac.caltech.edu/cgi-bin/nstedAPI/nph-nstedAPI?table=aliastable&objname="

ids = []
aliases = []
badstars = []
for j,star in enumerate(starnames):
    print(j,star)
    r = s.query_object(star)
    if r:
        tmp = r['IDS'][0].split('|')
    else:
        tmp = []
    r = requests.get(baseurl+star)
    if "ERROR" not in r.content: 
        tmp += r.content.strip().split("\n")
    tmp = list(np.unique(tmp))
    if 'aliasdis' in tmp: tmp.remove('aliasdis')
    if len(tmp) == 0:
        badstars.append(star)
        continue
    if star not in tmp: tmp.append(star)
    ids.append([j]*len(tmp))
    aliases.append(tmp)


#toggleoff = ['notesel','messel','bibsel','fluxsel','sizesel','mtsel','spsel','rvsel','pmsel','cooN','otypesel']
#url = """http://simbad.u-strasbg.fr/simbad/sim-id?output.format=ASCII&Ident=%s"""%starnames[j]
#for t in toggleoff:
#    url += "&obj.%s=off"%t




out3 = pandas.DataFrame({'SID': np.hstack(ids),
                         'Alias': np.hstack(aliases)
                         })

###################################################################


#------write to db------------
namemxchar = np.array([len(n) for n in plannames]).max()

#testdb
engine = create_engine('mysql+pymysql://ds264@127.0.0.1/dsavrans_plandb',echo=False)

#proddb#################################################################################################
username = 'dsavrans_admin'
passwd = keyring.get_password('plandb_sql_login', username)
if passwd is None:
    passwd = getpass.getpass("Password for mysql user %s:\n"%username)
    keyring.set_password('plandb_sql_login', username, passwd)

engine = create_engine('mysql+pymysql://'+username+':'+passwd+'@sioslab.com/dsavrans_plandb',echo=False)
#proddb#################################################################################################


data.to_sql('KnownPlanets',engine,chunksize=100,if_exists='replace',
        dtype={'pl_name':sqlalchemy.types.String(namemxchar),
               'pl_hostname':sqlalchemy.types.String(namemxchar-2),
               'pl_letter':sqlalchemy.types.CHAR(1)})
        
result = engine.execute("ALTER TABLE KnownPlanets ENGINE=InnoDB")
result = engine.execute("ALTER TABLE KnownPlanets ADD INDEX (pl_name)")
result = engine.execute("ALTER TABLE KnownPlanets ADD INDEX (pl_hostname)")
result = engine.execute("ALTER TABLE KnownPlanets ADD completeness double COMMENT 'completeness in 0.1 to 0.5 as, 22.5 dMag bin'")
result = engine.execute("UPDATE KnownPlanets SET completeness=NULL where completeness is not NULL")
result = engine.execute("ALTER TABLE KnownPlanets ADD compMinWA double COMMENT 'min non-zero completeness WA'")
result = engine.execute("ALTER TABLE KnownPlanets ADD compMaxWA double COMMENT 'max non-zero completeness WA'")
result = engine.execute("ALTER TABLE KnownPlanets ADD compMindMag double COMMENT 'min non-zero completeness dMag'")
result = engine.execute("ALTER TABLE KnownPlanets ADD compMaxdMag double COMMENT 'max non-zero completeness dMag'")


orbdata.to_sql('PlanetOrbits',engine,chunksize=100,if_exists='replace',dtype={'Name':sqlalchemy.types.String(namemxchar)})
result = engine.execute("ALTER TABLE PlanetOrbits ENGINE=InnoDB")
result = engine.execute("ALTER TABLE PlanetOrbits ADD INDEX (Name)")
result = engine.execute("ALTER TABLE PlanetOrbits ADD FOREIGN KEY (Name) REFERENCES KnownPlanets(pl_name) ON DELETE NO ACTION ON UPDATE NO ACTION");

#add comments
coldefs = pandas.ExcelFile('coldefs.xlsx')
coldefs = coldefs.parse('Sheet1')
cols = coldefs['Column'][coldefs['Definition'].notnull()].values
cdefs = coldefs['Definition'][coldefs['Definition'].notnull()].values


result = engine.execute("show create table KnownPlanets")
res = result.fetchall()
res = res[0]['Create Table']
res = res.split("\n")

p = re.compile('`(\S+)`[\s\S]+')
keys = []
defs = []
for r in res:
  r = r.strip().strip(',')
  if "COMMENT" in r: continue
  m = p.match(r)
  if m:
    keys.append(m.groups()[0])
    defs.append(r)


for key,d in zip(keys,defs):
  if not key in cols: continue
  comm =  """ALTER TABLE `KnownPlanets` CHANGE `%s` %s COMMENT "%s";"""%(key,d,cdefs[cols == key][0])
  print comm
  r = engine.execute(comm)




#---------------------------------------------
#write completeness table
for ind,c in zip(goodinds,cs):
    result = engine.execute("UPDATE KnownPlanets SET completeness=%f where pl_name = '%s'"%(c,plannames[ind]))

for ind,minw,maxw,mind,maxd in zip(goodinds,minCWA,maxCWA,minCdMag,maxCdMag):
    result = engine.execute("UPDATE KnownPlanets SET compMinWA=%f,compMaxWA=%f,compMindMag=%f,compMaxdMag=%f where pl_name = '%s'"%(minw,maxw,mind,maxd,plannames[ind]))



out2.to_sql('Completeness',engine,chunksize=100,if_exists='replace',dtype={'Name':sqlalchemy.types.String(namemxchar)})
result = engine.execute("ALTER TABLE Completeness ENGINE=InnoDB")
result = engine.execute("ALTER TABLE Completeness ADD INDEX (Name)")
result = engine.execute("ALTER TABLE Completeness ADD FOREIGN KEY (Name) REFERENCES KnownPlanets(pl_name) ON DELETE NO ACTION ON UPDATE NO ACTION");


#---------------------------------------------------
#write alias table
aliasmxchar = np.array([len(n) for n in out3['Alias'].values]).max()


out3.to_sql('Aliases',engine,chunksize=100,if_exists='replace',dtype={'Alias':sqlalchemy.types.String(aliasmxchar)})
result = engine.execute("ALTER TABLE Aliases ENGINE=InnoDB")
result = engine.execute("ALTER TABLE Aliases ADD INDEX (Alias)")
result = engine.execute("ALTER TABLE Aliases ADD INDEX (SID)")


