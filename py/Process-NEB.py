import numpy as np
import linecache as lc
import matplotlib.pyplot as plt
import os
from datetime import datetime
import sys
import re
import pdb
from matplotlib.ticker import MaxNLocator
import csv 

plt.style.use('seaborn-deep')
plt.rcParams['axes.prop_cycle'] = plt.cycler(color=['mediumblue', 'crimson','darkgreen', 'darkorange','crimson', 'darkorchid'])
#plt.rcParams['figure.figsize'] = [12,8]
plt.rcParams['axes.linewidth'] = 1.7
plt.rcParams['lines.linewidth'] = 6.0
#plt.rcParams['axes.grid'] = True
plt.rcParams['font.size'] = 12
plt.rcParams['font.family'] =  'sans-serif'
plt.rcParams["figure.autolayout"] = True

#conversion from kcal/mol to eV
conv=0.043361254529175
#I need to read a reax.dat file and a reax.log file and get values from both.

etol=sys.argv[3]
timestep=sys.argv[4]

def read_dat(file):
    my_list = []
    with open(file) as f:
        for line in f.readlines():
            x = line.split()
            if(len(x) == 8):
                vals = [int(x[0]), int(x[1]), float(x[2]),float(x[3]),float(x[4])]
                my_list.append(vals)
    f.close()
    return np.asarray(sorted(my_list, key=lambda x:x[0]))

def read_dump(file, hnum):
    my_list=[]
    with open(file) as f:
        lines=f.readlines()
        box = np.asarray([lines[5].split()[1],lines[6].split()[1],lines[7].split()[1]], dtype = float)
        for line in lines:
            x=line.split()
            if(len(x)==5):
                if(int(x[0]) == int(hnum)):
                    f.close()
                    return np.asarray([int(x[0]), float(x[2])*box[0], float(x[3])*box[1], float(x[4])*box[2]])
    f.close()
    return 


def read_log(file, mod=0):
    ar=[]
    with open(file) as f:
        cont=len(f.readlines())
        line = lc.getline(file,cont - mod).split()
    f.close()
    for val in line:
        ar.append(float(val))
    return np.asarray(ar)
#===============================================================
def MEP(file):
    #there are 9 elements before RD1
    last= read_log(file)
    prev = read_log(file,mod=1)
    R=last[9::2]                #points in replica space, RD1-RDN
    mep=last[10::2]*conv            #actual pE values, PE1-PEN
    ms = mep - np.min(mep)      #normalizing MEP
    efb=last[6]*conv               #forward barrier
    erb=last[7]*conv               #reverse barrier
    RD=last[8]                  #total reaction cood space
    return R, ms , efb, erb, RD

def plot_mep(path,file,fileID,hnum=0, xo= 0.01):
    r,pe,EF,ER, RD = MEP(file)
    my_barriers=[]
    points=[]
    mytext="FEB ={0:.3f} REB = {1:.3f}"
    indices, vals, nb = calc_barrier(file)
    if not (nb):
        points.append([0,0,0])
    else:
        for i in range(nb):
            l, p, s = vals[i]
            a,b,c = indices[i]
            feb = p-l
            reb = p-s
            print(mytext.format(feb,reb))
            my_barriers.append([feb,reb])
            points.append([r[a], r[b], r[c]])
            
    name=fileID
    
    fig = plt.figure(figsize=[6,6])
    plt.scatter(r,pe, marker = '^', color = 'darkgreen', s=180)
    #plt.plot(r,pe, linestyle = '--', linewidth = 3.0, color = 'darkgreen')
    #plt.scatter(points,vals, color='r', s=20)
    txt=(r"Forward E$_A $ = {0:.2f} eV"+"\n"
        + r"Reverse E$_A $ = {1:.2f} eV"+"\n").format(EF, ER)
    txt2 = "Replica distance={0:.2f}".format(RD) + r"$\AA $"
    plt.text(xo, np.max(pe)*0.8, txt, fontsize = 14)
    
    plt.text(xo, np.max(pe)*0.68, txt2,fontsize=14)
    plt.title(f"MEP with E-tol': {etol} & timestep: {timestep}")
    plt.ylabel("PE (eV)")
    plt.xlabel(r'$x_{replica} $')
    #plt.axes().yaxis.set_major_locator(MaxNLocator(integer=True))
    plt.grid('on',axis='y',linewidth=1)
    plt.savefig(path+name +"-NEB.png")
    
    return (EF,ER,my_barriers,RD)


def calc_barrier(file):
    r, pe, ef, er, rd = MEP(file)
    pe=pe
    low = pe[0]
    emin = 0
    peak = 0
    p_index =0
    m_index = 0
    low_index = 0
    ref =0.0
    climbing = True
    out_points = []
    out_vals =[]
    num_barriers = 0
    #pdb.set_trace()
    for i in range(3,len(pe)):
        if(climbing):
            if(pe[i] > ref):
                ref = pe[i]
                peak = pe[i]
                p_index = i
                continue
            else:
                climbing =False
        if not(climbing):
            #pdb.set_trace()
            if(pe[i] < ref):
                ref = pe[i]
                emin = pe[i]
                if(i == len(pe)-1):
                    out_points.append([low_index,p_index,i])
                    out_vals.append([low,peak, emin])
                    num_barriers+=1
                    continue
                else:
                    continue
            elif(pe[i-2]== peak):
                ref = pe[i]
                if(pe[i]> peak):
                    peak = pe[i]
                    p_index=i
                    climbing = True
                    continue
                else:
                    continue
            else:
                ref = pe[i]
                out_points.append([low_index,p_index,i])
                out_vals.append([low,peak, emin])
                low = emin
                low_index = i
                num_barriers+=1
                climbing = True
                continue
    if(num_barriers):
        return out_points, out_vals, num_barriers
    else:
        return [0,0,0] , [0,0,0] , 0


def savecsv(data,filename,col_names=None):

    csv_name=filename+'.csv'


    file_exists = os.path.isfile(filename)

    #data=runname+','+data+''
    with open(filename,'a',newline='', encoding='utf-8') as fd:
        csv_writer=csv.writer(fd)

        if file_exists is False and col_names is not None:
            csv_writer.writerow(col_names)
            
        csv_writer.writerow(data)

def catch(func, *args, handle=lambda e : e, **kwargs):
    try:
        return func(*args, **kwargs)
    except Exception as e:
        #print(handle(e))
        return None

if __name__=='__main__':
    #from tkinter.filedialog import askopenfilename
    atomID=sys.argv[2]
    removeID=sys.argv[5]
    
    fileID=atomID
    
    csvID=str(atomID)+'-'+str(removeID)
    
    #dirname="/home/agoga/documents/code/topcon-md/data/HNEB1/"#os.path.dirname(os.path.realpath(pth))
    
    
    dirname=sys.argv[1]
    file=f"{dirname}logs/{fileID}neb.log"
    
    
    
    
    ret=plot_mep(dirname,file,fileID)#,hnum)
    
    
    import numpy as np
    import PIL
    from PIL import Image

    list_im = [dirname+f"{fileID}-NEB.png",dirname+f"PES({fileID}).png",dirname+f"{fileID}-Ovito.png"]
    
    imgs=[]
    for i in list_im:
        im=catch(Image.open,i)
        if im is not None:
            imgs.append(im)
            
            
    # pick the image which is the smallest, and resize the others to match it (can be arbitrary image shape here)
    min_shape = sorted( [(np.sum(i.size), i.size ) for i in imgs])[0][1]
    imgs_comb = np.hstack([i.resize(min_shape) for i in imgs])

    # save that beautiful picture
    imgs_comb = Image.fromarray(imgs_comb)
    imgs_comb.save(dirname+f"NEB-PES-{fileID}.png")    
    
    splt=dirname[:-1].split("/")
    tname=splt[-1]#name of the output folder 'NEB125_1-0.01_11'
    second="/".join(splt[:-1])
    imgs_comb.save(second+"/NEB/"+tname[3:] +".png")
    
    
    
    
    
    #csvfile=second+"/NEB/"+csvID+".csv"
    csvfile=second+"/NEB/pairs.csv"
    
    col_names=["pair","etol","ts","dist","FEB","REB","A","B","C","D","E","F","G","H"]
    dat=[csvID,etol,timestep,ret[3],ret[0],ret[1]]
    
    for l in ret[2]:
        dat.append(l[0])
        dat.append(l[1])
        
    savecsv(dat,csvfile,col_names)
    # for p in list_im:
    #     try:
    #         os.remove(p)
    #     except:
    #         i=0


















