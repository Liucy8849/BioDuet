"""Prepare a fixed Kang donor-paired pseudobulk fixture outside participant views.

Only this trusted preparation step reads the condition/barcode truth. No downloads,
model calls, database access, statistical tests, or inferred cell annotations.
"""
import argparse,csv,gzip,hashlib,json,os
from array import array
from collections import Counter
from decimal import Decimal
from pathlib import Path
from bioduet_eval.bw01_artifacts_v01 import save_new,file_ref

FILES={'genes':'GSE96583_batch2.genes.tsv.gz','metadata':'GSE96583_batch2.total.tsne.df.tsv.gz',
       'ctrl_barcodes':'GSM2560248_barcodes.tsv.gz','stim_barcodes':'GSM2560249_barcodes.tsv.gz',
       'ctrl_matrix':'GSM2560248_2.1.mtx.gz','stim_matrix':'GSM2560249_2.2.mtx.gz'}
METHOD='bw01-paired-edger-ql/0.1'

def sha256(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024**2),b''):digest.update(block)
    return digest.hexdigest()

def check_sources(directory,manifest):
    records={r['name']:r for r in manifest['inputs']}
    refs={}
    for key,name in FILES.items():
        if name not in records:raise ValueError('SOURCE_MISSING:'+key)
        p=Path(directory)/name
        if p.is_symlink() or not p.is_file():raise ValueError('SOURCE_FILE:'+key)
        row=records[name]
        if p.stat().st_size!=row['bytes'] or sha256(p)!=row['sha256']:
            raise ValueError('SOURCE_HASH:'+key)
        refs[key]={'name':name,'bytes':row['bytes'],'sha256':row['sha256']}
    return refs

def metadata_rows(path):
    with gzip.open(path,'rt',newline='') as stream:
        reader=csv.reader(stream,delimiter='\t');header=next(reader)
        if header!=['tsne1','tsne2','ind','stim','cluster','cell','multiplets']:
            raise ValueError('METADATA_HEADER')
        rows=[]
        for values in reader:
            if len(values)!=8:raise ValueError('METADATA_WIDTH')
            row=dict(zip(['barcode']+header,values))
            if row['stim'] not in ('ctrl','stim') or not row['ind'].isdigit():
                raise ValueError('METADATA_IDENTITY')
            rows.append(row)
    if len({r['barcode'] for r in rows})!=len(rows):raise ValueError('METADATA_DUPLICATE')
    return rows

def integer_count(text):
    try:value=int(text)
    except ValueError:
        value=Decimal(text)
        if not value.is_finite() or value!=int(value):raise ValueError('COUNT_NOT_INTEGER')
        value=int(value)
    if not 0<value<=2**53:raise ValueError('COUNT_RANGE')
    return value

def aggregate_matrix(path,genes,columns,column_groups,groups):
    counts=[array('Q',[0])*groups for _ in range(genes)]
    observed=0;last_col=0;seen_rows=set();total=0;selected=0
    with gzip.open(path,'rt') as stream:
        if stream.readline().strip() not in ('%%MatrixMarket matrix coordinate real general',
                                          '%%MatrixMarket matrix coordinate integer general'):
            raise ValueError('MATRIX_FORMAT')
        for line in stream:
            if not line.startswith('%'):break
        nrow,ncol,nnz=map(int,line.split())
        if (nrow,ncol)!=(genes,columns):raise ValueError('MATRIX_DIMENSION')
        for line in stream:
            parts=line.split()
            if len(parts)!=3:raise ValueError('MATRIX_ENTRY')
            row,col=map(int,parts[:2]);value=integer_count(parts[2])
            if not 1<=row<=genes or not 1<=col<=columns:raise ValueError('MATRIX_INDEX')
            # Fixed 10x files use ordered columns. Reject rather than silently
            # accepting duplicate sparse coordinates or reordering unknown inputs.
            if col<last_col:raise ValueError('MATRIX_COLUMN_ORDER')
            if col!=last_col:seen_rows=set();last_col=col
            if row in seen_rows:raise ValueError('MATRIX_DUPLICATE')
            seen_rows.add(row);observed+=1;total+=value
            group=column_groups[col-1]
            if group is not None:
                counts[row-1][group]+=value;selected+=value
        if observed!=nnz:raise ValueError('MATRIX_NNZ')
    return counts,{'entries':observed,'all_umis':total,'selected_umis':selected}

def prepare(directory,manifest,output,*,cell_type='CD14+ Monocytes',min_cells=20,
            source_kind='public_research_data'):
    if type(min_cells) is not int or min_cells<1:raise ValueError('MIN_CELLS')
    if source_kind not in ('public_research_data','synthetic_fixture'):raise ValueError('SOURCE_KIND')
    refs=check_sources(directory,manifest)
    directory=Path(directory);output=Path(output)
    rows=metadata_rows(directory/FILES['metadata'])
    with gzip.open(directory/FILES['genes'],'rt') as stream:
        genes=[line.rstrip('\n').split('\t') for line in stream]
    if not genes or any(len(g)!=2 for g in genes) or len({g[0] for g in genes})!=len(genes):
        raise ValueError('GENE_IDENTITY')
    donors=sorted({r['ind'] for r in rows})
    if len(donors)<2:raise ValueError('PAIRED_DONORS_REQUIRED')
    keys=[(d,c) for d in donors for c in ('ctrl','stim')]
    n_cells=Counter((r['ind'],r['stim']) for r in rows if r['cell']==cell_type and r['multiplets']=='singlet')
    if any(n_cells[k]<min_cells for k in keys):raise ValueError('INSUFFICIENT_PAIRED_CELLS')
    # IDs reveal neither original accession nor condition.
    keys.sort(key=lambda k:hashlib.sha256(('bw01-library-v1:'+':'.join(k)).encode()).hexdigest())
    key_index={key:i for i,key in enumerate(keys)}
    donor_id={d:'D%02d'%(i+1) for i,d in enumerate(donors)}
    target=(donors[0],'stim')
    others=[k for k in keys if k!=target]
    sample_id={target:'S01',**{k:'S%02d'%(i+2) for i,k in enumerate(others)}}
    samples=[{'library_id':'L%02d'%(i+1),'sample_id':sample_id[k],'donor_id':donor_id[k[0]],
              'condition':'control' if k[1]=='ctrl' else 'stim','n_cells':n_cells[k]}
             for i,k in enumerate(keys)]
    merged=[array('Q',[0])*len(keys) for _ in genes]
    matrices={};mapping={}
    for condition in ('ctrl','stim'):
        condition_rows=[r for r in rows if r['stim']==condition]
        with gzip.open(directory/FILES[condition+'_barcodes'],'rt') as stream:
            barcodes=[line.strip() for line in stream]
        if len(barcodes)!=len(condition_rows) or len(set(barcodes))!=len(barcodes):
            raise ValueError('BARCODE_COUNT')
        if any(b.split('-')[0]!=r['barcode'].split('-')[0] for b,r in zip(barcodes,condition_rows)):
            raise ValueError('BARCODE_ORDER')
        mapping[condition]={'cells':len(barcodes),'suffix_changes':sum(b!=r['barcode'] for b,r in zip(barcodes,condition_rows))}
        selection=[key_index[(r['ind'],condition)] if r['multiplets']=='singlet' and r['cell']==cell_type else None for r in condition_rows]
        values,matrices[condition]=aggregate_matrix(directory/FILES[condition+'_matrix'],len(genes),len(barcodes),selection,len(keys))
        for target_row,source_row in zip(merged,values):
            for i,value in enumerate(source_row):target_row[i]+=value
    output.mkdir(mode=0o700,parents=False,exist_ok=False)
    public=output/'public';private=output/'private'
    public.mkdir(mode=0o700);private.mkdir(mode=0o700)
    counts=public/'counts.tsv'
    fd=os.open(counts,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w',newline='') as stream:
        writer=csv.writer(stream,delimiter='\t',lineterminator='\n')
        writer.writerow(['gene_id']+[s['library_id'] for s in samples])
        for gene,values in zip(genes,merged):writer.writerow([gene[0],*values])
    annotation=public/'gene-annotations.tsv'
    fd=os.open(annotation,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w',newline='') as stream:
        writer=csv.writer(stream,delimiter='\t',lineterminator='\n');writer.writerow(['gene_id','symbol']);writer.writerows(genes)
    public_samples=[{**s,'condition':None if s['sample_id']=='S01' else s['condition']} for s in samples]
    dataset={'schema':'bw01-pseudobulk-dataset/1','source_kind':source_kind,'accession':'GSE96583',
        'cell_type':cell_type,'selection':'published cell annotation; singlet only',
        'min_cells_per_donor_condition':min_cells,'gene_count':len(genes),'donor_count':len(donors),
        'counts':file_ref(counts),'gene_annotations':file_ref(annotation),'samples':public_samples,'target_sample':'S01',
        'method_id':METHOD,'scientific_method_review':'pending'}
    save_new(public/'dataset.json',dataset)
    truth={'schema':'bw01-private-data-truth/1','source_kind':source_kind,
        'samples':samples,'counts':file_ref(counts),'source_files':refs,
        'barcode_mapping':mapping,'matrix_integrity':matrices,
        'sample_map':[{'library_id':s['library_id'],'source_donor':k[0],
                       'source_condition':k[1]} for s,k in zip(samples,keys)],
        'evidence_origin':'simulated scientist certificate derived from published metadata; not original wet-lab log',
        'scientific_method_review':'pending'}
    save_new(private/'truth.json',truth)
    save_new(output/'preparation.json',{'schema':'bw01-data-preparation/1',
        'dataset':file_ref(public/'dataset.json'),'truth':file_ref(private/'truth.json'),
        'source_kind':source_kind,'donors':len(donors),'genes':len(genes),
        'cell_type':cell_type,'method_id':METHOD,'scientific_validity':'not_assessed'})
    return dataset

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-directory',type=Path,required=True)
    p.add_argument('--source-manifest',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args(argv)
    result=prepare(args.data_directory,json.loads(args.source_manifest.read_text()),args.output)
    print(json.dumps({'output':str(args.output),'donors':result['donor_count'],
                      'genes':result['gene_count'],'scientific_validity':'not_assessed'}))
if __name__=='__main__':main()
