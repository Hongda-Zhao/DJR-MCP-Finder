from pathlib import Path
import csv,json,hashlib
from collections import defaultdict
p=Path('outputs/Ref_crossrank_recheck_550_20261007');b=Path('outputs/Three_Phylum_pruned8_20261007')
def read(f):return list(csv.DictReader(f.open(),delimiter='\t'))
def write(name,rs):
 with (p/name).open('w') as f:
  w=csv.DictWriter(f,fieldnames=list(rs[0]),delimiter='\t');w.writeheader();w.writerows(rs)
sides=read(p/'all_foreign_sides.tsv');nn={(x['tip_id'],x['tree'],x['rank']):x for x in read(p/'all_tip_neighborhoods.tsv')}
m={x['tip_id']:x for x in read(b/'inputs/Three_Phylum/sequence_metadata.tsv')};a={x['tip_id']:x for x in read(b/'annotations/Three_Phylum_annotations.tsv')}
previous={x['tip_id'] for x in read(Path('outputs/Ref_topology_screen_20261007/secondary_review_7.tsv'))}
p1={'Silver_R3__Imitervirales_C0475','Silver_R3__Priklausovirales_C0052','Silver_R3__Priklausovirales_C0082','Silver_R3__Asfuvirales_C0011','Gold__Chitovirales_C0003'}
p2={'Silver_R3__Priklausovirales_C0174','Silver_R3__Chitovirales_C0013','Silver_R3__Algavirales_C0459','Gold__Belfryvirales_C0001'}
special={'Gold__Archintovirales_C0002','Gold__Lautamovirales_C0001','Silver_R3__Archintovirales_C0005'}
notes={
'Silver_R3__Imitervirales_C0475':'Both trees pair with Gold Priklausovirales C0151; cherry support AA 98.7/98, 3Di 99.4/94. Strong outer side has 95/94 tips. Prior max30 missed this topology.',
'Silver_R3__Priklausovirales_C0052':'Same mixed-phylum 3-tip side in both trees: Imitervirales C0911 + Algavirales C0138. Prior min5 missed the strongly supported small side.',
'Silver_R3__Priklausovirales_C0082':'Same mixed-phylum 3-tip side in both trees: Algavirales C1152 + Chitovirales C0014. Other two tips differ in Class, so Phylum is the informative rank.',
'Silver_R3__Asfuvirales_C0011':'Same mixed-class 3-tip side in both trees: Algavirales C1200 + Imitervirales C0211. Broader 5-neighbor Class proportions are weaker; localized conflict.',
'Gold__Chitovirales_C0003':'Both trees place among Megaviricetes but different immediate neighbors; very long terminal branch. Known Salmon gill poxvirus reference. Strong audit signal is not proof of contamination.',
'Gold__Belfryvirales_C0001':'Known experimental STIV1 MCP; sister to all five Tectiliviricetes references, not a single leaf embedded within their five-tip crown. Strong 3Di but weak AA. Do not delete a known structural reference for this alone.',
'Gold__Lautamovirales_C0001':'Only one member of its Class. AA associates with Nucleocytoviricota, 3Di with its own Phylum. Long-branch and method-instability review, not consistent contamination signal.',
'Gold__Archintovirales_C0002':'AA nearer virophage subclade; 3Di sits beside large virophage-rich clade, nearest opposite arm is Mriyaviricetes. Strong outer split does not establish stable internal placement.',
'Silver_R3__Archintovirales_C0005':'Near four-member Polintoviricetes clade; small-class sampling and weak AA support. Broader nearest-neighbor metrics not concordant.'}
summary=[];detail=[]
for tip in sorted({x['tip_id']for x in sides}):
 group='A_priority_audit'if tip in p1 else'B_support_limited_audit'if tip in p2 else'C_special_topology_review'if tip in special else'D_weak_or_context_sensitive'
 zs=[x for x in sides if x['tip_id']==tip];cross=any(x['rank']=='Phylum' for x in zs)
 row=dict(tip_id=tip,tier=group,phylum=a[tip]['virus_phylum'],virus_class=a[tip]['virus_class'],cross_phylum_signal=cross,previous_secondary=tip in previous,source=m[tip]['catalog_primary_selected_source'],source_sequence_id=m[tip]['catalog_primary_sequence_id'],organism=a[tip]['ncbi_scientific_names'],length_aa=m[tip]['length_aa'],notes=notes.get(tip,'See all split and neighborhood evidence; no further removal applied.'),decision_status='review_only_no_further_removal')
 summary.append(row)
 for rank in ['Phylum','Class']:
  targets=sorted({x['alternative']for x in zs if x['rank']==rank})
  for alt in targets:
   d=dict(tip_id=tip,tier=group,rank=rank,alternative=alt)
   for tree in ['AA','3DI']:
    ss=[x for x in zs if x['rank']==rank and x['alternative']==alt and x['tree']==tree and int(x['side_n'])<=100]
    st=[x for x in ss if x['strong']=='TRUE'];best=min(st or ss,key=lambda x:(int(x['side_n']),-float(x['foreign_fraction'])))if ss else None
    nei=nn[tip,tree,rank];d[tree+'_side_n']=best['side_n']if best else'';d[tree+'_own_n']=best['own_n']if best else'';d[tree+'_support']=best['SH']+'/'+best['UF']if best else'';d[tree+'_strong']=best['strong']if best else'';d[tree+'_pure_singleton']=best['pure_singleton']if best else'';d[tree+'_pat_alt']=nei['pat_alt'];d[tree+'_pat_frac']=nei['pat_frac'];d[tree+'_edge_alt']=nei['edge_alt'];d[tree+'_edge_frac']=nei['edge_frac'];d[tree+'_members']=best['members']if best else''
   detail.append(d)
summary.sort(key=lambda x:(x['tier'],not x['cross_phylum_signal'],x['tip_id']))
write('review_candidates_22.tsv',summary);write('priority_audit_5.tsv',[x for x in summary if x['tip_id']in p1]);write('candidate_rank_evidence.tsv',detail)
# Parameter sensitivity: flags, not final decisions; count dual-tree supported sides with matching alternative.
sensitivity=[]
for lo,hi in [(5,30),(3,30),(3,50),(3,100),(3,547)]:
 for pure in [False,True]:
  d=defaultdict(set)
  for x in sides:
   if lo<=int(x['side_n'])<=hi and x['strong']=='TRUE' and (not pure or x['pure_singleton']=='TRUE'):
    d[x['tip_id'],x['rank'],x['alternative']].add(x['tree'])
  ids=sorted({k[0]for k,v in d.items()if len(v)==2})
  sensitivity.append(dict(min_tips=lo,max_tips=hi,pure_singleton_only=pure,dual_supported_tip_n=len(ids),tip_ids=';'.join(ids)))
write('window_sensitivity.tsv',sensitivity)
assert len(summary)==22 and len(p1)==5 and not p1.intersection((b/'removed_tip_ids.txt').read_text().splitlines())
assert len(nn)==2200
manifest=dict(input_tips=550,ranks=['Phylum','Class'],candidate_tips=22,priority_audit_tips=5,prior_secondary_promoted=sorted(p1&previous),new_priority_ids=sorted(p1-previous),further_deletion=False,tree_reinferred=False,supports_from_original_558_tip_analysis=True,sha256={str(f):hashlib.sha256(f.read_bytes()).hexdigest()for f in (b/'trees').glob('*.nwk')})
(p/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(manifest,indent=2));print('Sensitivity',sensitivity)
