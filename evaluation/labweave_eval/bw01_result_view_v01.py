"""Participant-visible summary of actual candidate output; no private truth."""
import csv,hashlib,math
from pathlib import Path
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def summarize(directory,dataset,public_directory):
    annotations=Path(public_directory)/'gene-annotations.tsv'
    if digest(annotations)!=dataset['gene_annotations']['sha256']:raise ValueError('ANNOTATION_IDENTITY')
    with annotations.open(newline='') as f:
        labels={r['gene_id']:r['symbol'] for r in csv.DictReader(f,delimiter='\t')}
    path=Path(directory)/'de.tsv';rows=[];seen=set()
    with path.open(newline='') as f:
        reader=csv.DictReader(f,delimiter='\t')
        if reader.fieldnames!=['gene_id','logFC','logCPM','F','PValue','FDR']:raise ValueError('RESULT_SCHEMA')
        for r in reader:
            if r['gene_id'] in seen or r['gene_id'] not in labels:raise ValueError('RESULT_GENE')
            seen.add(r['gene_id'])
            values={k:float(r[k]) for k in ['logFC','logCPM','F','PValue','FDR']}
            if any(not math.isfinite(v) for v in values.values()) or not 0<=values['FDR']<=1 or not 0<=values['PValue']<=1:
                raise ValueError('RESULT_VALUE')
            rows.append(r)
            if len(rows)>100000:raise ValueError('RESULT_LIMIT')
    if not rows:raise ValueError('EMPTY_RESULTS')
    selected=[r for r in rows if float(r['FDR'])<=0.05]
    ordered=sorted(rows,key=lambda r:(float(r['FDR']),r['gene_id']))[:10]
    return {'source':'actual_candidate_de_tsv','result_sha256':digest(path),
        'analysis_unit':'donor','contrast':'stim minus control','donors':dataset['donor_count'],
        'cell_type':dataset['cell_type'],'tested_genes':len(rows),'fdr_threshold':'0.05',
        'significant_genes':len(selected),
        'significant_up':sum(float(r['logFC'])>0 for r in selected),
        'significant_down':sum(float(r['logFC'])<0 for r in selected),
        'top_genes':[{'gene_id':r['gene_id'],'symbol':labels[r['gene_id']],'logFC':r['logFC'],
                      'PValue':r['PValue'],'FDR':r['FDR']} for r in ordered],
        'interpretation_limit':'method-specific paired donor contrast; does not establish causation or independent biological validation'}
