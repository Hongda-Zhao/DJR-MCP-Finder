"""Create a separate development-only, three-head exclusion experiment."""
import csv,hashlib,json,shutil,sys
from pathlib import Path
from collections import Counter,defaultdict
from datetime import datetime,timezone
import numpy as np
import yaml
ROOT=Path('/aptmp/hongda/DJR-MCP-Finder/experiments/pruned30_dev_20261007')
BASE=Path('/aptmp/hongda/DJR-MCP-Finder')
ARCHIVE=Path('/aptmp/hongda/DJRMCP_Develope/project-V0__data-curation-V3__final-minimization__20260724/05_archived_paths')
MODELS=['esmc_6b','esm2_650m']
def sha(p):
 h=hashlib.sha256()
 with p.open('rb')as f:
  for block in iter(lambda:f.read(4*1024*1024),b''):h.update(block)
 return h.hexdigest()
def read(p):
 with p.open()as f:return list(csv.DictReader(f,delimiter='\t'))
def write(p,rows):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('w',newline='')as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]),delimiter='\t',lineterminator='\n');w.writeheader();w.writerows(rows)
def js(p,x):p.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n')
if (ROOT/'PREPARED.json').exists():raise SystemExit('Already prepared; validate existing artifacts rather than overwrite')
for d in ['data','configs','code','embeddings','results','logs']:(ROOT/d).mkdir(parents=True,exist_ok=True)
# Copy computational implementation; no edits to frozen production code.
shutil.copytree(BASE/'src',ROOT/'code/src',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__'))
for f in ['calibrate_benchmark_model.py','freeze_benchmark_cv_folds.py']:
 shutil.copy2(BASE/'scripts'/f,ROOT/'scripts'/f)
sys.path.insert(0,str(ROOT/'code/src'))
from djrmcp_finder.config import load_config
from djrmcp_finder.cv_folds import freeze_cv_fold_map,load_frozen_cv_fold_map
from djrmcp_finder.stages.classifier import _validate_embedding_contract
original=BASE/'data/processed/v0/master_manifest.tsv'
original_sha=sha(original)
assert original_sha=='94aa5aff80a18367d36c06fb2f51155f3b52bd8fff4b5be2aa682d891ab84dc7'
allrows=read(original);excluded={r['sequence_sha256']for r in read(ROOT/'exclusion_crosswalk_30.tsv')}
assert len(excluded)==30 and len(allrows)==11060
hits=[r for r in allrows if r['sequence_sha256']in excluded];assert len(hits)==30
removed=[r for r in hits if r['split']in ['train','validation']];testflags=[r for r in hits if r['split']=='test']
assert Counter(r['split']for r in removed)=={'train':16,'validation':7} and len(testflags)==7
selected=[r for r in allrows if not(r['sequence_sha256']in excluded and r['split']in ['train','validation'])]
assert len(selected)==11037
assert [r for r in selected if r['split']=='test']==[r for r in allrows if r['split']=='test']
components=defaultdict(set)
for r in selected:components[r['global_component_id']].add(r['split'])
assert all(len(v)==1 for v in components.values())
manifest=ROOT/'data/master_manifest.tsv';write(manifest,selected)
write(ROOT/'data/excluded_development_23.tsv',removed);write(ROOT/'data/flagged_test_7_unchanged.tsv',testflags)
# Source FASTA remains on the server. Create a filtered derivative with verified hashes.
source_fasta=BASE/'data/interim/v0/model_representatives.faa';seqs={};key=None
for line in source_fasta.read_text().splitlines():
 if line.startswith('>'):key=line[1:].split()[0];seqs[key]=''
 else:seqs[key]+=line.strip()
fasta=ROOT/'data/model_representatives.faa'
with fasta.open('w')as f:
 for row in selected:
  sequence=seqs[row['protein_id']]
  assert len(sequence)==int(row['length_aa']) and hashlib.sha256(sequence.encode()).hexdigest()==row['sequence_sha256']
  f.write('>'+row['protein_id']+'\n'+sequence+'\n')
baseconfig=BASE/'configs/model_benchmark_v0_metric_revision_1.yaml';config=load_config(baseconfig)
config.pop('config_lineage',None)
config['project'].update(version='pruned30-development-three-head-retraining-20261007',test_evaluation_permitted=False,experiment_status='experimental_not_production')
config['benchmark']['models']={m:config['benchmark']['models'][m]for m in MODELS}
config['paths'].update(v0_manifest=str(manifest),v0_fasta=str(fasta),benchmark_embedding_root=str(ROOT/'embeddings'),benchmark_embedding_overrides={},benchmark_result_root=str(ROOT/'results'),benchmark_cv_fold_map=str(ROOT/'data/frozen_global_component_folds.tsv'),benchmark_cv_fold_metadata=str(ROOT/'data/frozen_global_component_folds.json'),dataset_output=str(ROOT/'data'),known_output=str(ROOT/'data/unused_known'),embedding_output=str(ROOT/'embeddings/placeholder'),result_output=str(ROOT/'results/placeholder'))
config['experiment']={'excluded_sequence_sha_count':30,'development_excluded':23,'test_flagged_but_unchanged':7,'policy':'exclude_from_all_three_development_heads','group_components':'retain_original_component_and_outer_split_membership','cv_policy':'rebuild_train_only_5_fold_map_once_shared_by_both_models','source_manifest_sha256':original_sha,'source_config_sha256':sha(baseconfig),'test_performance_prohibited':True,'post_hoc_phylogeny_guided_curation':True}
configpath=ROOT/'configs/experiment.yaml';configpath.write_text(yaml.safe_dump(config,sort_keys=False))
retained_indices=[i for i,r in enumerate(allrows)if not(r['sequence_sha256']in excluded and r['split']in ['train','validation'])]
reports=[]
for model in MODELS:
 source=BASE/'data/processed/embeddings/v0_benchmark_esm2_650m'if model=='esm2_650m'else ARCHIVE/'data/processed/embeddings/v0_benchmark_esmc_6b'
 for line in (source/'CHECKSUMS.sha256').read_text().splitlines():
  digest,name=line.split(maxsplit=1);name=name.lstrip('*');assert sha(source/name)==digest,(model,name,'checksum failed')
 oldmeta=json.loads((source/'metadata.json').read_text());assert oldmeta['manifest_sha256']==original_sha and oldmeta['status']=='complete'
 assert oldmeta['resolved_model_revision']==config['benchmark']['models'][model]['model_revision']
 oldrows,vectors=_validate_embedding_contract(original,source)
 assert oldrows==allrows and vectors.shape[0]==11060 and np.isfinite(vectors).all()
 complete=np.load(source/'completed.npy');assert complete.shape==(11060,) and complete.all()
 dest=ROOT/'embeddings'/('v0_benchmark_'+model);dest.mkdir(exist_ok=False)
 values=np.asarray(vectors[retained_indices]);np.save(dest/'embeddings.float16.npy',values);np.save(dest/'completed.npy',complete[retained_indices])
 index=read(source/'index.tsv');newindex=[]
 for newrow,oldrow in enumerate(retained_indices):
  r=dict(index[oldrow]);r['embedding_row']=str(newrow);newindex.append(r)
 write(dest/'index.tsv',newindex)
 metadata=dict(oldmeta);metadata.update(manifest_sha256=sha(manifest),fasta_sha256=sha(fasta),record_count=len(selected),completed_records=len(selected))
 metadata['derivation']={'operation':'exact_row_subset_no_embedding_recomputation','created_utc':datetime.now(timezone.utc).isoformat(),'source_bundle':str(source),'source_metadata_sha256':sha(source/'metadata.json'),'source_checksums_sha256':sha(source/'CHECKSUMS.sha256'),'source_manifest_sha256':original_sha,'removed_development_records':23,'test_rows_unchanged':True,'original_compute_fields_inherited_not_new_timings':True}
 js(dest/'metadata.json',metadata)
 filenames=['completed.npy','embeddings.float16.npy','index.tsv','metadata.json']
 (dest/'CHECKSUMS.sha256').write_text(''.join(sha(dest/f)+'  '+f+'\n'for f in filenames))
 newmanifest,newvectors=_validate_embedding_contract(manifest,dest)
 assert newmanifest==selected and np.array_equal(newvectors,values)
 report={'model':model,'source_bundle':str(source),'shape':list(newvectors.shape),'source_checksums_verified':True,'exact_subset_verified':True,'metadata_sha256':sha(dest/'metadata.json')};reports.append(report)
 print(json.dumps(report),flush=True)
# Freeze one new component-safe fold map shared by both models; never resplit outer Test.
fold=freeze_cv_fold_map(config);load_frozen_cv_fold_map(config,manifest)
assert sha(original)==original_sha
counts={'rows':len(selected),'split_counts':dict(Counter(r['split']for r in selected)),'vma_by_split':dict(Counter(r['split']for r in selected if r['head2_label']=='viral_morphogenesis_associated')),'h3_known_by_split':dict(Counter(r['split']for r in selected if r['head3_known_mask']=='1'))}
assert counts['split_counts']=={'train':6618,'validation':2205,'test':2214}
report={'status':'prepared_and_validated','counts':counts,'bundle_reports':reports,'fold_contract':fold,'source_manifest_unchanged':True,'test_rows_unchanged':True,'test_predictions_or_metrics_computed':False,'new_manifest_sha256':sha(manifest),'config_sha256':sha(configpath),'source_code_sha256':{str(f.relative_to(ROOT)):sha(f)for f in (ROOT/'code/src').rglob('*.py')}}
js(ROOT/'PREPARED.json',report);print(json.dumps({'status':report['status'],'counts':counts}),flush=True)
