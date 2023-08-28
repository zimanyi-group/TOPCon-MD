#!/usr/bin/env python
from lammps import lammps
import sys
import os

import numpy as np
from mpi4py import MPI
from matplotlib import pyplot as plt
from random import gauss

from mpl_toolkits.axes_grid1 import make_axes_locatable
from ovito.io import import_file, export_file
from ovito.data import *
from ovito.modifiers import *
from ovito.vis import Viewport
from ovito.vis import TachyonRenderer
import matplotlib.gridspec as gridspec
import matplotlib as mpl
from argparse import ArgumentParser


class MidpointNormalize(mpl.colors.Normalize):
    def __init__(self, vmin, vmax, midpoint=0, clip=False):
        self.midpoint = midpoint
        mpl.colors.Normalize.__init__(self, vmin, vmax, clip)

    def __call__(self, value, clip=None):
        normalized_min = max(0, 1 / 2 * (1 - abs((self.midpoint - self.vmin) / (self.midpoint - self.vmax))))
        normalized_max = min(1, 1 / 2 * (1 + abs((self.vmax - self.midpoint) / (self.midpoint - self.vmin))))
        normalized_mid = 0.5
        x, y = [self.vmin, self.midpoint, self.vmax], [normalized_min, normalized_mid, normalized_max]
        return np.ma.masked_array(np.interp(value, x, y))

def find_atom_position(L,atomI):
    L.commands_string(f'''
        variable x{atomI} equal x[{atomI}]
        variable y{atomI} equal y[{atomI}]
        variable z{atomI} equal z[{atomI}]
        ''')
    
    x = L.extract_variable(f'x{atomI}')
    y = L.extract_variable(f'y{atomI}')
    z = L.extract_variable(f'z{atomI}')
    
    return (x,y,z)

def NEB_min(L):
    L.commands_string(f'''minimize {etol} {etol} 10000 10000''')

def init_dump(L,file,dumpstep):
    #Initialize and load the dump file
    L.commands_string(f'''
        clear
        units         real
        dimension     3
        boundary    p p p
        atom_style  charge
        atom_modify map yes

        variable seed equal 12345
        variable NA equal 6.02e23
 

        variable printevery equal 100
        variable restartevery equal 0#500000
        variable datapath string "data/"
        timestep {dt}

        variable massSi equal 28.0855 #Si
        variable massO equal 15.9991 #O
        variable massH equal  1.00784 #H
        
        region sim block 0 1 0 1 0 1

        lattice diamond {a}

        create_box 3 sim

        read_dump {file} {dumpstep} x y z box yes add keep
        
        mass         3 $(v_massH)
        mass         2 $(v_massO)
        mass         1 $(v_massSi)

        lattice none 1.0
        min_style quickmin
        
        pair_style	    reaxff potential/topcon.control 
        pair_coeff	    * * potential/ffield_Nayir_SiO_2019.reax Si O H

        neighbor        2 bin
        neigh_modify    every 10 delay 0 check no
        
        thermo $(v_printevery)
        thermo_style custom step temp density press vol pe ke etotal #flush yes
        thermo_modify lost ignore
        
        fix r1 all qeq/reax 1 0.0 10.0 1e-6 reaxff
        compute c1 all property/atom x y z''')
    
def init_dat(L,file):

    L.commands_string(f'''
        clear
        units         real
        dimension     3
        boundary    p p p
        atom_style  charge
        atom_modify map yes


        #atom_modify map array
        variable seed equal 12345
        variable NA equal 6.02e23

        timestep {dt}

        variable printevery equal 100
        variable restartevery equal 0
        variable datapath string "data/"


        variable massSi equal 28.0855 #Si
        variable massO equal 15.9991 #O
        variable massH equal  1.00784 #H
        

        read_data {file}
        
        mass         3 $(v_massH)
        mass         2 $(v_massO)
        mass         1 $(v_massSi)


        min_style quickmin
        
        pair_style	    reaxff potential/topcon.control
        pair_coeff	    * * potential/ffield_Nayir_SiO_2019.reax Si O H

        neighbor        2 bin
        neigh_modify    every 10 delay 0 check no
        
        thermo $(v_printevery)
        thermo_style custom step temp density press vol pe ke etotal #flush yes
        thermo_modify lost ignore
        
        region sim block EDGE EDGE EDGE EDGE EDGE EDGE
        
        fix r1 all qeq/reax 1 0.0 10.0 1e-6 reaxff
        compute c1 all property/atom x y z

        ''')

def create_ovito_plot(infile,figureName,atoms,infofile):
    yslabwidth=7#ang
    try:

        pipeline = import_file(infile)
        y=0
        l=len(atoms)
        yposlist=[]
        expr=""
        for i in range(l):
            id=atoms[i][0]
            ypos=atoms[i][1][1]

            yposlist.append(ypos)
            
            
            expr+=f'ParticleIdentifier=={id}'
            if i != l-1:
                expr+='||'
        
        ymin=min(yposlist)
        ymax=max(yposlist)
        ywidth=ymax-ymin
        
        
        if ywidth > yslabwidth:
            yslabwidth = ywidth+1
        ymid=(ymax+ymin)/2
        
        print(f"{yposlist}-mid:{ymid} width:{yslabwidth}")
        
        pipeline.modifiers.append(ExpressionSelectionModifier(expression = expr))
        pipeline.modifiers.append(AssignColorModifier(color=(0, 1, 0)))
        #pipeline.modifiers.append(SliceModifier(normal=(1,0,0),distance=x,slab_width=xzslabwidth))
        pipeline.modifiers.append(SliceModifier(normal=(0,1,0),distance=ymid,slab_width=yslabwidth))  
        #pipeline.modifiers.append(SliceModifier(normal=(0,0,1),distance=z,slab_width=xzslabwidth))
        
        data=pipeline.compute()
        data.cell.vis.enabled = False  
        
        pipeline.add_to_scene()
        vp = Viewport()
        vp.type = Viewport.Type.Front
        imagesize=(800,600)
        vp.zoom_all(size=imagesize)
        
        # for i in range(20):
        #     print(vp.camera_pos)
        # vp.__setattr__("camera_pos",(x,vp.camera_pos[1],z))
        # vp.camera_pos[0]=x
        # vp.camera_pos[2]=z
        
        vp.render_image(size=imagesize, filename=figureName,renderer=TachyonRenderer(ambient_occlusion=False, shadows=False))
        
        pipeline.remove_from_scene()
        if me==0:
            #write info file
            with open(infofile,'a') as f:
                f.write(f"image {figureName}\n")
    except Exception as e:
        print(e)
        
def reduce_sim_box(L,rpos):
    xi=rpos[0]
    yi=rpos[1]
    zi=rpos[2]
    bbox= L.extract_box()
    bbox=[[bbox[0][0],bbox[1][0]],[bbox[0][1],bbox[1][1]],[bbox[0][2],bbox[1][2]]]
    
    
    xrange = [max(xi-buff*xzhalfwidth,  bbox[0][0]),    min(xi+buff*xzhalfwidth,    bbox[0][1])]
    yrange = [max(yi-buff*xzhalfwidth,  bbox[1][0]),    min(yi+buff*xzhalfwidth,    bbox[1][1])]
    zrange = [max(zi-buff*xzhalfwidth,  bbox[2][0]),    min(zi+buff*xzhalfwidth,    bbox[2][1])]

    L.commands_string(f'''
        
        region ins block {xrange[0]} {xrange[1]} {yrange[0]} {yrange[1]} {zrange[0]} {zrange[1]} units box 
        region outs intersect 2 sim ins side out
        delete_atoms region outs compress no
        
        change_box all x final {xrange[0]} {xrange[1]} y final {yrange[0]} {yrange[1]} z final {zrange[0]} {zrange[1]} units box 
        
        run 0''')


def create_PES(L,atom):

    xi, yi, zi = find_atom_position(L,atom)
    ri=(xi,yi,zi)

    Ei = L.extract_compute('thermo_pe',0,0)*conv
    Ef=0

    
    elist=np.zeros([xlen,zlen])
    tot = xlen*zlen
    i=1
    
    if skipPES != 1:
        for j in range(zlen):
            for k in range(xlen):
            
                y=0
                
                x=xlist[k]
                z=zlist[j]
                
                xf = xi + x
                yf = yi
                zf = zi + z
                
                print(f"Step {i}/{tot}")
                
                L.commands_string(f'''
                    set atom {atom} x {xf} y {yf} z {zf}
                    run 0
                    ''')
                i+=1
                Ef = L.extract_compute('thermo_pe',0,0)*conv
                dE=Ef-Ei
                elist[j,k]=dE
            
    # #place the atom back where it came from!
    L.commands_string(f'''
        set atom {atom} x {xi} y {yi} z {zi}
        run 0
        ''')

    return [L,elist,ri]#returning the file names of the initial position and the final neb xyz file

def plot_PES(PESimage,markerPts,xlist,zlist,elist,title):
    #Plotting below
    fig,ax = plt.subplots(figsize=(6,6))
    
     # set maximum value of the PES to be twice the lowest E or 18eV, whichever is highest
    minE=np.min(elist)
    maxE=np.max(elist)
    ab=maxE
    
    
    # if abs(minE) >ab:
    #     ab=abs(minE)
    # max=12
    # if minE < -max:
    #     minE=-max
    # if maxE > max:
    #     maxE=max
        
    # elist[elist<-max]=-max
    # elist[elist>max]=max
    #minE=-maxE
    # maxE=2*abs(minE)
    # if maxE<18:
    #     maxE=18
    # elist[elist>maxE]=maxE
    
    
    # if finalLoc is not None:
    #     redXPts[1]=[finalLoc[0],finalLoc[1]]
    norm = MidpointNormalize(vmin=minE,vmax=maxE,midpoint=0)
    if maxE==0 and minE ==0:
        norm=None
        
    im=plt.contourf(zlist,xlist,elist,20,cmap='bwr',norm=norm)
    
    for m in markerPts:
        pts=m[1]
        plt.scatter(pts[0],pts[1],marker=m[0],c='g',)
        
    plt.grid('on',linewidth=0.25,linestyle='--')

    plt.axis('scaled')
    plt.xlabel('Δx(Å)')
    plt.ylabel('Δz(Å)',labelpad=0.05)
    
    
    divider = make_axes_locatable(ax)
    cax = divider.append_axes('right', size='5%', pad=0.05)
    cbar=fig.colorbar(im,cax=cax,orientation='vertical')
    cbar.set_label('ΔE(eV)')
    ax.set_title(title)
    #ax.set_xticklabels(np.arange(-math.floor(xzhalfwidth),math.floor(xzhalfwidth)+1,2))
    plt.savefig(PESimage)
    
    ###OLD working double PES ovito
    # fig = plt.figure(figsize=(12,6))
    # gs = gridspec.GridSpec(1, 2,width_ratios=[1,1.6])
    # ax1 = plt.subplot(gs[0])
    # ax2 = plt.subplot(gs[1])
    
    # #Load the atomistic view and put it in the second subplot
    # ovitoImage=plt.imread(ovitoFig)
    # ax2.axis('off')
    # ax2.imshow(ovitoImage,cmap='gray')
    
    
    # redXPts=np.transpose([[0,0],[rMin[0],rMin[1]]])
    
    
    # # if finalLoc is not None:
    # #     redXPts[1]=[finalLoc[0],finalLoc[1]]
        
    # im=ax1.contourf(zlist,xlist,elist,20,cmap='viridis')
    # ax1.scatter(redXPts[0],redXPts[1],marker='x',c='r')

    # ax1.axis('scaled')
    # ax1.set_xlabel('Δx(Å)')
    # ax1.set_ylabel('Δz(Å)')
    
    
    # divider = make_axes_locatable(ax1)
    # cax = divider.append_axes('right', size='5%', pad=0.15)
    # cbar=fig.colorbar(im,cax=cax,orientation='vertical')
    # cbar.set_label('ΔE(kcal/mol)')
    # ax1.set_title(f"Potential energy landscape around atom {atom}")
    # plt.savefig(PESimage)



def extract_box(L):
    bbox=L.extract_box()
    return np.array([[bbox[0][0],bbox[1][0]],[bbox[0][1],bbox[1][1]],[bbox[0][2],bbox[1][2]]])


def recenter_sim(L,r):
    
    bbox= extract_box(L)

    xhlen=abs(bbox[0][1]-bbox[0][0])/2
    yhlen=abs(bbox[1][1]-bbox[1][0])/2
    zhlen=abs(bbox[2][1]-bbox[2][0])/2
    print(xhlen)
    print(xhlen-r[0])
    
    L.commands_string(f'''
        
        #displace_atoms all move {xhlen-r[0]} {yhlen-r[1]} {zhlen-r[2]}
        displace_atoms all move {xhlen-r[0]} {yhlen-r[1]} 0
        run 0''')
    
    return bbox
    
# def prep_neb_zap(file,dumpstep,atomI,outfolder,atomF,plot):
#     plt.rcParams["figure.autolayout"] = True
    
#     #Need two lammps instances so that when removing an atom and minimizing we don't increase time for final NEB image minimization
#     L1 = lammps('mpi',["-log",f'{outfolder}/logs/PrepNEB-I.log'])
#     L2 = lammps('mpi',["-log",f'{outfolder}/logs/PrepNEB-F.log'])

    
#     fileIdent=f'{atomI}'

#     reset1=outfolder+f'{fileIdent}-NEBI.dump'
#     reset2=outfolder+f'{fileIdent}-NEBF.dump'
#     nebI=outfolder+f'{fileIdent}-NEBI.data'
#     nebF=outfolder+f'{fileIdent}-NEBF.data'
#     full= outfolder+ f'{fileIdent}-Full.data'
    
#     PESimage=outfolder+f"PES({fileIdent}).png"
#     ovitoFig=outfolder+f"{fileIdent}-Ovito.png"
    
    
    
    
#     #initilize the data files 
#     if file.endswith(".dump"):
#         LT = lammps('mpi',["-log",f'{outfolder}/logs/PrepNEB-LT.log'])
#         #do this first initialize to get around reaxff issues(charge stuff I think)
#         init_dump(LT,file,dumpstep)
#         LT.commands_string(f'''
#             write_data {full}
#             ''')
#         #
#         init_dat(L1,full)
#         init_dat(L2,full)
        
#     elif file.endswith(".data") or file.endswith(".dat"):
#         init_dat(L1,file)
#         init_dat(L2,file)
#     else:
#         print("File is not a .data or .dump")
#         return
    
    
#     ##### L1 - create the initial NEB data file
#     ri = find_atom_position(L1,atomI)
#     rf = find_atom_position(L1,atomF)
#     icoord=ri#have to use the coordinates before recentering
#     fcoord=rf
    
#     bbox=recenter_sim(L1,ri)


#     ri = find_atom_position(L1,atomI)
#     NEB_min(L1)
#     L1.commands_string(f'''
#     write_data {nebI}
#     ''')
    
#     ri = find_atom_position(L1,atomI)
    
     
#     if me == 0 and plot:
#         selection=[[atomI,ri],[atomF,rf]]
#         #Now create ovito plot of atoms for future use
#         create_ovito_plot(nebI,ovitoFig,ri,atomI,selection)
    
#     ret = create_PES(L1,atomI)
#     elist=ret[1]
    
#     rf = find_atom_position(L1,atomF)
#     ri = find_atom_position(L1,atomI)

#     #delete the output file so that we can rewrite it without the atom
#     try:
#         if me == 0:
#             os.remove(nebI)
#     except:
#         print("bad os fail - Proc %d out of %d procs" % (comm.Get_rank(),comm.Get_size()))
#         return
#     ###
#     # Now we start deleting atoms
#     # After deleting atoms we will save then load the data so that lammps resets all the charges do not have a net charge
#     ###
    
#     #delete the atom at the final location
#     L1.commands_string(f'''
#         group gFAtom id {atomF}
#         delete_atoms group gFAtom compress no
#         reset_timestep 0
#         write_dump all atom {reset1}
#     ''')
#     L1f = lammps('mpi',["-log",f'{outfolder}/logs/PrepNEB-If.log'])
#     init_dump(L1f,reset1,0)
#     NEB_min(L1f)
#     ri = find_atom_position(L1f,atomI)
#     L1f.commands_string(f'''
#         write_data {nebI}
#         ''')
    
#     #now print info for the final data file
#     if me==0:
#         #now write to the info file
#         with open(infofile,'a') as f:
#             f.write(f"pcsv_{fileIdent}_iPos [{icoord[0]},{icoord[1]},{icoord[2]}]\n")
#             f.write(f"pcsv_{fileIdent}_fPos [{fcoord[0]},{fcoord[1]},{fcoord[2]}]\n")
#             f.write(f"pcsv_{fileIdent}_box [[{bbox[0][0]},{bbox[0][1]}],[{bbox[1][0]},{bbox[1][1]}],[{bbox[2][0]},{bbox[2][1]}]]\n")
    
    
    
    
#     #####L2 - create the final NEB data file
#     ri = find_atom_position(L2,atomI)
#     recenter_sim(L2,ri)  
    
#     ri = find_atom_position(L2,atomI)
#     NEB_min(L2)

    
#     rf2 = find_atom_position(L2,atomF)
    
    
#     #delete the atom at the final location and reload using a dump file so that lammps resets charges
#     L2.commands_string(f'''
#         group gFAtom id {atomF}
#         delete_atoms group gFAtom compress no
#         reset_timestep 0
#         write_dump all atom {reset2}
#     ''')
#     L2f = lammps('mpi',["-log",f'{outfolder}/logs/PrepNEB-Ff.log'])
#     init_dump(L2f,reset2,0)
    
    
#     xyz=outfolder+f'{fileIdent}-NEBFXYZ.data'
#     #now create the lowest energy position data file for NEB.
#     L2f.commands_string(f'''
#                 set atom {atomI} x {rf2[0]} y {rf2[1]} z {rf2[2]}
                
#                 run 0
#                 write_data {xyz}
#     ''')
    
#     NEB_min(L2f)
    
#     rf2 = find_atom_position(L2f,atomI)
    

#     plottitle=f"Potential energy landscape around atom {atomI}"
#     redXPts=np.transpose([[0,0]])
#     allPts=[['x',redXPts]]
    
#     if skipPES != 1 and me==0:
#         plot_PES(PESimage,allPts,xlist,zlist,elist,plottitle)
    
    
#     ####Now clean up the dump file to be the correct format for NEB runs
#     if me == 0:## ONLY RUN ON ONE PROCESS
        
#         with open(nebF,'w+') as f:
#             f.write(f"1 \n{atomI} {rf2[0]} {rf2[1]} {rf2[2]}")
#     return

def get_lammps(log):
    return lammps('mpi',["-log",log,'-screen','none'])


def prep_neb_zap_single(file,dumpstep,atomI,atomF,outfolder,infofile,plot):
    plt.rcParams["figure.autolayout"] = True
    
    #Need two lammps instances so that when removing an atom and minimizing we don't increase time for final NEB image minimization
    L1 = get_lammps(f'{outfolder}/logs/PrepNEB-I.log')
    L2 = get_lammps(f'{outfolder}/logs/PrepNEB-F.log')

    
    fileIdent=f'{atomI}-{atomF}'

    reset1=outfolder+f'{fileIdent}-NEBI.dump'
    reset2=outfolder+f'{fileIdent}-NEBF.dump'
    nebI=outfolder+f'{fileIdent}-NEBI.data'
    nebF=outfolder+f'{fileIdent}-NEBF.data'
    full= outfolder+ f'{fileIdent}-Full.data'
    
    PESimage=outfolder+f"PES({fileIdent}).png"
    ovitoFig=outfolder+f"{fileIdent}-Ovito.png"
    
    selection=[atomI,atomF]
    
    
    #initilize the data files 
    if file.endswith(".dump"):
        LT = get_lammps(f'{outfolder}/logs/PrepNEB-LT.log')
        #do this first initialize to get around reaxff issues(charge stuff I think)
        init_dump(LT,file,dumpstep)
        LT.commands_string(f'''
            write_data {full}
            ''')
        #
        init_dat(L1,full)
        init_dat(L2,full)
        
    elif file.endswith(".data") or file.endswith(".dat"):
        init_dat(L1,file)
        init_dat(L2,file)
    else:
        print("File is not a .data or .dump")
        return
    
    
    ##### L1 - create the initial NEB data file
    ri = find_atom_position(L1,atomI)
    rf = find_atom_position(L1,atomF)
    
        
    if me==0:
        #write info file
        with open(infofile,'a') as f:
            f.write(f"zap\n")
            f.write(f"neb 0 {atomI} {fileIdent} {nebI} {nebF} {fileIdent}.log {atomI}\n"+#bash file is expecting a h atom after log file
                    f"initial-dat-0 {nebI}\n"+
                    f"final-dat-0 {nebF}\n"
                    )
    
    
    icoord=ri#have to use the coordinates before recentering
    fcoord=rf
    
    bbox=recenter_sim(L1,ri)


    ri = find_atom_position(L1,atomI)
    NEB_min(L1)
    L1.commands_string(f'''
    write_data {nebI}
    ''')
    
    ri = find_atom_position(L1,atomI)
    rf = find_atom_position(L1,atomF)
     
    if me == 0 and plot:
        #Now create ovito plot of atoms for future use
        atoms=[[atomI,ri],[atomF,rf]]
        create_ovito_plot(nebI,ovitoFig,atoms,infofile)
    
    ret = create_PES(L1,atomI)
    elist=ret[1]
    
    rf = find_atom_position(L1,atomF)
    ri = find_atom_position(L1,atomI)

    #delete the output file so that we can rewrite it without the atom
    try:
        if me == 0:
            os.remove(nebI)
    except:
        print("bad os fail - Proc %d out of %d procs" % (comm.Get_rank(),comm.Get_size()))
        return
    ###
    # Now we start deleting atoms
    # After deleting atoms we will save then load the data so that lammps resets all the charges do not have a net charge
    ###
    
    #delete the atom at the final location
    L1.commands_string(f'''
        group gFAtom id {atomF}
        delete_atoms group gFAtom compress no
        reset_timestep 0
        write_dump all atom {reset1}
    ''')
    L1f = get_lammps(f'{outfolder}/logs/PrepNEB-If.log')
    init_dump(L1f,reset1,0)
    NEB_min(L1f)
    ri = find_atom_position(L1f,atomI)
    L1f.commands_string(f'''
        write_data {nebI}
        ''')
    
    if me==0:
        #now write to the info file
        with open(infofile,'a') as f:
            f.write(f"pcsv_{fileIdent}_iPos [{icoord[0]},{icoord[1]},{icoord[2]}]\n")
            f.write(f"pcsv_{fileIdent}_fPos [{fcoord[0]},{fcoord[1]},{fcoord[2]}]\n")
            f.write(f"pcsv_{fileIdent}_box [[{bbox[0][0]},{bbox[0][1]}],[{bbox[1][0]},{bbox[1][1]}],[{bbox[2][0]},{bbox[2][1]}]]\n")
    
    
    
    #####L2 - create the final NEB data file
    ri = find_atom_position(L2,atomI)
    recenter_sim(L2,ri)
    
    ri = find_atom_position(L2,atomI)
    NEB_min(L2)

    
    rf2 = find_atom_position(L2,atomF)
    
    
    #delete the atom at the final location and reload using a dump file so that lammps resets charges
    L2.commands_string(f'''
        group gFAtom id {atomF}
        delete_atoms group gFAtom compress no
        reset_timestep 0
        write_dump all atom {reset2}
    ''')
    L2f = get_lammps(f'{outfolder}/logs/PrepNEB-Ff.log')
    init_dump(L2f,reset2,0)
    
    
    xyz=outfolder+f'{fileIdent}-NEBFXYZ.data'
    #now create the lowest energy position data file for NEB.
    L2f.commands_string(f'''
                set atom {atomI} x {rf2[0]} y {rf2[1]} z {rf2[2]}
    ''')
    

    L2f.commands_string(f'''       
                run 0
                write_data {xyz}
    ''')
    
    NEB_min(L2f)
    
    rf2 = find_atom_position(L2f,atomI)
    

        

    plottitle=f"Potential energy landscape around atom {atomI}"
    redXPts=np.transpose([[0,0]])
    allPts=[['x',redXPts]]
    
    if skipPES != 1 and me==0:
        plot_PES(PESimage,allPts,xlist,zlist,elist,plottitle)
    
    
    ####Now clean up the dump file to be the correct format for NEB runs
    if me == 0:## ONLY RUN ON ONE PROCESS
        
        with open(nebF,'w+') as f:
            f.write(f'''1\n{atomI} {rf2[0]} {rf2[1]} {rf2[2]}''')

            
            
                
    return


def prep_neb_zap_multi(file,dumpstep,atomI,aditionalAtoms,atomF,outfolder,infofile,plot,skipPES=True):
    
    print(f"{atomI}-{aditionalAtoms[0]} zapping {atomF}")
    plt.rcParams["figure.autolayout"] = True
    
    #Need two lammps instances so that when removing an atom and minimizing we don't increase time for final NEB image minimization
    L1 = lammps('mpi',["-log",f'{outfolder}/logs/PrepNEB-I.log'])
    L2 = lammps('mpi',["-log",f'{outfolder}/logs/PrepNEB-F.log'])

    
    fileIdent=f'{atomI}'

    reset1=outfolder+f'{fileIdent}-NEBI.dump'
    reset2=outfolder+f'{fileIdent}-NEBF.dump'
    nebI=outfolder+f'{fileIdent}-NEBI.data'
    nebF=outfolder+f'{fileIdent}-NEBF.data'
    full= outfolder+ f'{fileIdent}-Full.data'
    
    PESimage=outfolder+f"PES({fileIdent}).png"
    ovitoFig=outfolder+f"{fileIdent}-Ovito.png"
    
    selection=[atomI,atomF]
    
    
    #initilize the data files 
    if file.endswith(".dump"):
        LT = lammps('mpi',["-log",f'{outfolder}/logs/PrepNEB-LT.log'])
        #do this first initialize to get around reaxff issues(charge stuff I think)
        init_dump(LT,file,dumpstep)
        LT.commands_string(f'''
            write_data {full}
            ''')
        #
        init_dat(L1,full)
        init_dat(L2,full)
        
    elif file.endswith(".data") or file.endswith(".dat"):
        init_dat(L1,file)
        init_dat(L2,file)
    else:
        print("File is not a .data or .dump")
        return
    
    
    ##### L1 - create the initial NEB data file
    ri = find_atom_position(L1,atomI)
    rf = find_atom_position(L1,atomF)
    
    extraMovers=[]
    for aa in aditionalAtoms:
        rai = find_atom_position(L1,aa)
        #get the seperation vector between the mover and any extra movers
        tpos = [rai[0]-ri[0],rai[1]-ri[1],rai[2]-ri[2]]
        extraMovers.append([aa,tpos])
        
    if me==0:
        #write info file
        with open(infofile,'a') as f:
            f.write(f"multizap {len(aditionalAtoms)+1}\n")
            f.write(f"neb 0 {atomI} {fileIdent} {nebI} {nebF} {fileIdent}-{atomF}.log {extraMovers[0][0]}\n"+#bash file is expecting a h atom after log file
                    f"initial-dat-0 {nebI}\n"+
                    f"final-dat-0 {nebF}\n"
                    )
    
    
    icoord=ri#have to use the coordinates before recentering
    fcoord=rf
    
    bbox=recenter_sim(L1,ri)


    ri = find_atom_position(L1,atomI)
    NEB_min(L1)
    L1.commands_string(f'''
    write_data {nebI}
    ''')
    
    ri = find_atom_position(L1,atomI)
    
     
    if me == 0 and plot:
        #Now create ovito plot of atoms for future use
        create_ovito_plot(nebI,ovitoFig,ri,atomI,selection)
    
    ret = create_PES(L1,atomI)
    elist=ret[1]
    
    rf = find_atom_position(L1,atomF)
    ri = find_atom_position(L1,atomI)

    #delete the output file so that we can rewrite it without the atom
    try:
        if me == 0:
            os.remove(nebI)
    except:
        print("bad os fail - Proc %d out of %d procs" % (comm.Get_rank(),comm.Get_size()))
        return
    ###
    # Now we start deleting atoms
    # After deleting atoms we will save then load the data so that lammps resets all the charges do not have a net charge
    ###
    
    #delete the atom at the final location
    L1.commands_string(f'''
        group gFAtom id {atomF}
        delete_atoms group gFAtom compress no
        reset_timestep 0
        write_dump all atom {reset1}
    ''')
    L1f = lammps('mpi',["-log",f'{outfolder}/logs/PrepNEB-If.log'])
    init_dump(L1f,reset1,0)
    NEB_min(L1f)
    ri = find_atom_position(L1f,atomI)
    L1f.commands_string(f'''
        write_data {nebI}
        ''')
    
    if me==0:
        #now write to the info file
        with open(infofile,'a') as f:
            f.write(f"pcsv_{fileIdent}_iPos [{icoord[0]},{icoord[1]},{icoord[2]}]\n")
            f.write(f"pcsv_{fileIdent}_fPos [{fcoord[0]},{fcoord[1]},{fcoord[2]}]\n")
            f.write(f"pcsv_{fileIdent}_box [[{bbox[0][0]},{bbox[0][1]}],[{bbox[1][0]},{bbox[1][1]}],[{bbox[2][0]},{bbox[2][1]}]]\n")
    
    
    
    #####L2 - create the final NEB data file
    ri = find_atom_position(L2,atomI)
    recenter_sim(L2,ri)
    
    ri = find_atom_position(L2,atomI)
    NEB_min(L2)

    
    rf2 = find_atom_position(L2,atomF)
    
    
    #delete the atom at the final location and reload using a dump file so that lammps resets charges
    L2.commands_string(f'''
        group gFAtom id {atomF}
        delete_atoms group gFAtom compress no
        reset_timestep 0
        write_dump all atom {reset2}
    ''')
    L2f = lammps('mpi',["-log",f'{outfolder}/logs/PrepNEB-Ff.log'])
    init_dump(L2f,reset2,0)
    
    
    xyz=outfolder+f'{fileIdent}-NEBFXYZ.data'
    #now create the lowest energy position data file for NEB.
    L2f.commands_string(f'''
                set atom {atomI} x {rf2[0]} y {rf2[1]} z {rf2[2]}
    ''')
    
    for ex in extraMovers:
        L2f.commands_string(f'''
                set atom {ex[0]} x {rf2[0]+ex[1][0]} y {rf2[1]+ex[1][1]} z {rf2[2]+ex[1][2]}
        ''')
    
    L2f.commands_string(f'''       
                run 0
                write_data {xyz}
    ''')
    
    NEB_min(L2f)
    
    rf2 = find_atom_position(L2f,atomI)
    
    finalPosAdd=[]
    for aa in aditionalAtoms:

        raf= find_atom_position(L2f,aa)
        print(raf)
        finalPosAdd.append([aa,raf])
        

    plottitle=f"Potential energy landscape around atom {atomI}"
    redXPts=np.transpose([[0,0]])
    allPts=[['x',redXPts]]
    
    if skipPES != 1 and me==0:
        plot_PES(PESimage,allPts,xlist,zlist,elist,plottitle)
    
    
    ####Now clean up the dump file to be the correct format for NEB runs
    if me == 0:## ONLY RUN ON ONE PROCESS
        
        with open(nebF,'w+') as f:
            numAdd=len(aditionalAtoms)
            f.write(f'''{numAdd+1}\n{atomI} {rf2[0]} {rf2[1]} {rf2[2]}''')
            for a in finalPosAdd:
                f.write(f"\n{a[0]} {a[1][0]} {a[1][1]} {a[1][2]}")
            
            
                
    return

def prep_neb_multi_jump(args):
    currentIfile=nebI=args.dfile
    atomI=args.atomid
    outfolder=args.out
    infofile=args.info
    
    
    
    
    
    
    bondcenter_list=args.bclist.split(',')#list of pairs of atoms whose bond center is the final position
    i=9
    
    # for j in range(numjumps):
    #     bondcenter_list.append([int(sys.argv[i+j]),int(sys.argv[i+j+1])])
    #     i+=1
        
    jumps=len(bondcenter_list)
    
    with open(infofile,'a') as f:
        if me==0:
            print(f"Num jumpes {jumps}")
            f.write(f"multijump {jumps}\n")

        
        for i in range(jumps):
            identifier=f"j{i}"
            bc=bondcenter_list[i].split()
            ba1=int(bc[0])
            ba2=int(bc[1])
            

            # # fposx=bc[0]
            # # fposy=bc[1]
            # # fposz=bc[2]
            
            # fpos=[fposx,fposy,fposz]
            
            (nebI, nebF,nebFfullData) =prep_neb_to_bond_center(args,identifier,ba1,ba2,datafile=currentIfile)
            
            if me==0:
                f.write(f"neb {i} {atomI} {identifier} {nebI} {nebF} {identifier}-{atomI}.log {atomI}\n"+#bash file is expecting a h atom after log file
                        f"{identifier}-atoms {bc[0]} {bc[1]}\n"+
                        f"initial-dat-{i} {nebI}\n"+
                        f"final-dat-{i} {nebF}\n"
                        )
            currentIfile=nebFfullData#start the next jump where the last left off
        
def midpt(p1,p2):
    midpt=[0,0,0]
    for i in range(len(p1)):
        midpt[i]=(p1[i]+p2[i])/2
    return midpt


def prep_neb_to_bond_center(args,ident,atomF1,atomF2,datafile=None,dumpstep=0):
    outfolder=args.out
    atomI=args.atomid
    
    infofile=args.info
    if datafile is None:
        datafile=args.dfile
        
    L1 = get_lammps(f'{outfolder}/logs/PrepNEB-If.log')
    
    fileIdent=f'{atomI}-{ident}'
    
    full= outfolder+ f'{fileIdent}-Full.data'
    
    #initilize the data files 
    if datafile.endswith(".dump"):
        LT = get_lammps(f'{outfolder}/logs/PrepNEB-LT.log')
        #do this first initialize to get around reaxff issues(charge stuff I think)
        init_dump(LT,datafile,dumpstep)
        LT.commands_string(f'''
            write_data {full}
            ''')
        #
        init_dat(L1,full)
        
    elif datafile.endswith(".data") or datafile.endswith(".dat"):
        init_dat(L1,datafile)
    else:
        print("File is not a .data or .dump")
        return

    rf1 = find_atom_position(L1,atomF1)
    rf2 = find_atom_position(L1,atomF2)
    
    midpoint=midpt(rf1,rf2)
    if me==0:
        print(f"{rf1} {rf2} {midpoint}")
    return prep_neb_to_location(args,ident,fileIdent,midpoint,L1=L1,dumpstep=dumpstep)
    


def prep_neb_to_location(args,fileIdent,ident,fpos,datafile=None,L1=None,dumpstep=0):
    outfolder=args.out
    atomI=args.atomid
    if datafile is None:
        datafile=args.dfile
    infofile=args.info
    plt.rcParams["figure.autolayout"] = True
    nebI=outfolder+f'{fileIdent}-NEBI.data'
    nebF=outfolder+f'{fileIdent}-NEBF.data'
    
    
    if L1 is None:
        if me==0:
            #now write to the info file
            with open(infofile,'a') as f:
                f.write(f"neb 0 {atomI} {ident} {nebI} {nebF} {ident}-{atomI}.log {atomI}\n")
        
        L1 = get_lammps(f'{outfolder}/logs/PrepNEB-L1.log')
        full= outfolder+ f'{fileIdent}-Full.data'
        if datafile.endswith(".dump"):
            LT = get_lammps(f'{outfolder}/logs/PrepNEB-LT.log')
            #do this first initialize to get around reaxff issues(charge stuff I think)
            init_dump(LT,datafile,dumpstep)
            LT.commands_string(f'''
                write_data {full}
                ''')
            init_dat(L1,full)
            
        elif datafile.endswith(".data") or datafile.endswith(".dat"):
            init_dat(L1,datafile)
        else:
            print("File is not a .data or .dump")
            return
        
    
    
    #Need two lammps instances so that when removing an atom and minimizing we don't increase time for final NEB image minimization

    
    
    
    # PESimage=outfolder+f"PES({fileIdent}).png"
    
    bbox=extract_box(L1)
    ##### L1 - create the initial NEB data file
    ri = find_atom_position(L1,atomI)

    icoord=ri#have to use the coordinates before recentering
    
    # bbox=recenter_sim(L1,ri)
    ri = find_atom_position(L1,atomI)
    NEB_min(L1)
    L1.commands_string(f'''
    write_data {nebI}
    ''')
    
    ri = find_atom_position(L1,atomI)
     
    # if me == 0 and plot:
    #     #Now create ovito plot of atoms for future use
    #     create_ovito_plot(nebI,ovitoFig,ri,atomI,selection)
    
    
    if me==0:
        #now write to the info file
        with open(infofile,'a') as f:
            
            f.write(f"pcsv_{ident}_iPos [{icoord[0]},{icoord[1]},{icoord[2]}]\n")
            f.write(f"pcsv_{ident}_fPos [{fpos[0]},{fpos[1]},{fpos[2]}]\n")
            f.write(f"pcsv_{ident}_box [[{bbox[0][0]},{bbox[0][1]}],[{bbox[1][0]},{bbox[1][1]}],[{bbox[2][0]},{bbox[2][1]}]]\n")

    
    xyz=outfolder+f'{fileIdent}-NEBFXYZ.data'
    
    
    #now create the lowest energy position data file for NEB.
    L1.commands_string(f'''
                set atom {atomI} x {fpos[0]} y {fpos[1]} z {fpos[2]}
    ''')
    NEB_min(L1)
    L1.commands_string(f'''
                run 0
                write_data {xyz}
                ''')
    
    rf = find_atom_position(L1,atomI)
    
    # print(f"Initial POS for atom{atomI}: {ri}")
    # print(f"Final POS for atom{atomI}: {rf}")
    
    
    ####Now clean up the dump file to be the correct format for NEB runs
    if me == 0:## ONLY RUN ON ONE PROCESS
        
        with open(nebF,'w+') as f:
            f.write(f"1 \n{atomI} {rf[0]} {rf[1]} {rf[2]}")
    return (nebI,nebF,xyz)
    

   
    
if __name__ == "__main__":
    
    parser = ArgumentParser()
    parser.add_argument('--style')
    parser.add_argument('--out')
    parser.add_argument('--etol')
    parser.add_argument('--ts')
    parser.add_argument('--dfile')
    parser.add_argument('--atomid',type=int)
    parser.add_argument('--plot')
    parser.add_argument('--bclist')
    parser.add_argument('--info')
    args=parser.parse_args()
    
    dt=args.ts
    etol=args.etol
    me = MPI.COMM_WORLD.Get_rank()
    # print(args)

    a=5.43
    #conversion from kcal/mol to eV
    conv=0.043361254529175

    xzhalfwidth = 20.1
    yhwidth=5.1
    step = .5
    buff=1

    xlist=np.arange(-xzhalfwidth,xzhalfwidth,step)
    zlist=np.arange(-xzhalfwidth,xzhalfwidth,step)

    xlen=len(xlist)
    zlen=len(zlist)
    
    
    
    
    # xpos=float(sys.argv[8])
    # ypos=float(sys.argv[9])
    # zpos=float(sys.argv[10])
    # fpos=[xpos,ypos,zpos]
    # prep_neb_to_location(datafile,dumpstep,atomI,fpos,fileIdent,ident,outfolder,infofile)
    
    
    # zapID=int(sys.argv[8])
    # hID=int(sys.argv[9])
    # nebfiles=prep_neb_zap_multi(datafile,dumpstep,atomI,[hID],zapID,outfolder,infofile,plot)
    # print(f"{atomI}-{hID} zapping {zapID}")
    
    
    # zapID=int(sys.argv[8])
    # prep_neb_zap_single(datafile,dumpstep,atomI,zapID,outfolder,infofile,plot)
    
    #print(f"{outfolder} {etol} {dt} {datafile} {atomI} {numjumps} {bondcenter_list}")
    if args.style=='multijump':
        nebFiles =prep_neb_multi_jump(args)#,datafile,dumpstep,atomI,outfolder,infofile,plot)
    
    

    MPI.Finalize()
    exit()