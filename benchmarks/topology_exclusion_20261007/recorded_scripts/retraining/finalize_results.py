import csv,json,hashlib,math
from pathlib import Path
ROOT=Path('/aptmp/hongda/DJR-MCP-Finder/experiments/pruned30_dev_20261007')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return list(csv.DictReader(p.open(),delimiter='\t'))
prep=json.loads((ROOT/'PREPARED.json').read_text());manifest=ROOT/'data/master_manifest.tsv'
assert sha(manifest)==prep['new_manifest_sha256']
original=Path('/aptmp/hongda/DJR-MCP-Finder/data/processed/v0/master_manifest.tsv')
assert sha(original)=='94aa5aff80a18367d36c06fb2f51155f3b52bd8fff4b5be2aa682d891ab84dc7'
rows=read(manifest);orig=read(original);excluded={r['sequence_sha256']for r in read(ROOT/'exclusion_crosswalk_30.tsv')}
assert not any(r['sequence_sha256']in excluded for r in rows if r['split']!='test')
assert [r for r in rows if r['split']=='test']==[r for r in orig if r['split']=='test']
output=[];fold=None;heads=['head1','head2','head3_phylum'];files=[]
for model in ['esmc_6b','esm2_650m']:
 root=ROOT/'results'/model;cal=json.loads((root/'calibration.json').read_text());cv=json.loads((root/'metrics/cross_validation.json').read_text());val=json.loads((root/'metrics/validation_metrics.json').read_text())
 assert cal['test_evaluated']is False and cal['manifest_sha256']==sha(manifest)
 assert set(cal['heads'])==set(cv['heads'])==set(val['heads'])==set(heads)
 assert cal['cv_fold_contract']==cv['cv_fold_contract']
 if fold is None:fold=cal['cv_fold_contract']
 else:assert cal['cv_fold_contract']==fold
 assert cal['embedding_metadata_sha256']==sha(ROOT/'embeddings'/('v0_benchmark_'+model)/'metadata.json')
 for h in heads:
  item=cal['heads'][h];assert sha(Path(item['model_path']))==item['model_sha256']
  assert item['temperature']>0 and math.isfinite(item['temperature'])
  assert not item['temperature_search']['coarse_boundary_hit'] and not item['temperature_search']['fine_boundary_hit']
  scores=cv['heads'][h]['candidates_ranked'][0]
  assert scores['parameter']==item['best_parameter'] and len(scores['fold_scores'])==5
  assert abs(sum(scores['fold_scores'])/5-scores['mean_score'])<1e-12
  assert sum(x['heldout_record_count']for x in cv['heads'][h]['fold_diagnostics'])=={'head1':6618,'head2':618,'head3_phylum':305}[h]
 assert val['heads']['head1']['n']==2205 and val['heads']['head2']['n']==205 and val['heads']['head3_phylum']['n']==100
 means={h:cv['heads'][h]['candidates_ranked'][0]['mean_score']for h in heads}
 output.append({'model':model,'CV_H1_AP':means['head1'],'CV_H2_AP':means['head2'],'CV_H3_macro_F1':means['head3_phylum'],'CV_composite_S':.6*means['head1']+.3*means['head2']+.1*means['head3_phylum'],'Validation_H1_AP':val['heads']['head1']['average_precision'],'Validation_H1_MCC':val['heads']['head1']['mcc'],'Validation_H2_macro_F1':sum(val['heads']['head2']['f1_by_class'])/2,'Validation_H3_closed_macro_F1':val['heads']['head3_phylum']['closed_set_macro_f1'],'Validation_H3_unknown_as_error_macro_F1':val['heads']['head3_phylum']['macro_f1_unknown_as_error'],'Validation_H3_unknown_recall':cal['heads']['head3_phylum']['open_set']['validation_unknown_recall'],'Validation_H3_unknown_n':cal['heads']['head3_phylum']['open_set']['validation_unknown_diagnostic_n'],'test_evaluated':False})
 files.extend(p for p in root.rglob('*')if p.is_file())
 assert not any('test' in p.name.lower()for p in root.rglob('*')if p.is_file())
with (ROOT/'comparison.tsv').open('w')as f:
 w=csv.DictWriter(f,fieldnames=list(output[0]),delimiter='\t');w.writeheader();w.writerows(output)
report={'status':'both_models_three_heads_completed_and_verified','models':output,'data_counts':prep['counts'],'same_manifest_and_cv_folds':True,'six_model_checksums_verified':True,'test_rows_unchanged':True,'test_predictions_or_metrics_computed':False,'original_manifest_unchanged':True,'production_model_replaced':False,'execution':'PBS SMALL; workstation available but training had already completed before migration','new_manifest_sha256':sha(manifest)}
(ROOT/'RESULTS_SUMMARY.json').write_text(json.dumps(report,indent=2)+'\n')
files.extend([ROOT/'PREPARED.json',ROOT/'RESULTS_SUMMARY.json',ROOT/'comparison.tsv',manifest,ROOT/'configs/experiment.yaml'])
(ROOT/'EXPERIMENT_CHECKSUMS.sha256').write_text(''.join(sha(p)+'  '+str(p.relative_to(ROOT))+'\n'for p in sorted(files)))
print(json.dumps(report,indent=2))
