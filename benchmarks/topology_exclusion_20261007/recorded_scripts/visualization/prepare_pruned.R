options(stringsAsFactors=FALSE,expressions=50000)
suppressPackageStartupMessages(library(ape))
source('outputs/Three_Phylum_RefOnly_FoldMason_IQTREE_20260924/visualization_latest/tree_helpers.R')
src<-'outputs/Three_Phylum_RefOnly_FoldMason_IQTREE_20260924';out<-'outputs/Three_Phylum_pruned30_20261007'
exclude<-c(read.delim('outputs/Ref_topology_screen_20261007/priority_quarantine_review_8.tsv',check.names=FALSE)$tip_id,read.delim('outputs/Ref_crossrank_recheck_550_20261007/review_candidates_22.tsv',check.names=FALSE)$tip_id)
secondary<-read.delim('outputs/Ref_topology_screen_20261007/secondary_review_7.tsv',check.names=FALSE)$tip_id
stopifnot(length(exclude)==30,!anyDuplicated(exclude))
dir.create(file.path(out,'trees'),showWarnings=FALSE,recursive=TRUE)
qas<-list();maps<-list()
for(kind in c('aa','3di')){
 original<-read.tree(file.path(src,'iqtree/Three_Phylum',kind,'reference.treefile'))
 stopifnot(length(original$tip.label)==558,all(exclude%in%original$tip.label))
 kept<-sort(setdiff(original$tip.label,exclude)); stopifnot(sum(secondary%in%kept)==3)
 orig_dist<-cophenetic(original)[kept,kept]
 ds<-descendant_tips(original)
 key<-function(ids){a<-sort(match(ids,kept));b<-setdiff(seq_along(kept),a);if(!length(a)||!length(b))return('');sa<-paste(a,collapse=',');sb<-paste(b,collapse=',');if(length(a)<length(b))sa else if(length(b)<length(a))sb else min(sa,sb)}
 projected<-data.frame(original_child=original$edge[,2],key=vapply(original$edge[,2],function(v)key(intersect(original$tip.label[ds[[v]]],kept)),''),length=original$edge.length,support='')
 ints<-projected$original_child>length(original$tip.label);projected$support[ints]<-original$node.label[projected$original_child[ints]-length(original$tip.label)];projected$support[is.na(projected$support)]<-''
 pruned<-drop.tip(original,exclude,trim.internal=TRUE,collapse.singles=TRUE)
 stopifnot(length(pruned$tip.label)==528,setequal(pruned$tip.label,kept),all(pruned$edge.length>=0))
 err<-max(abs(cophenetic(pruned)[kept,kept]-orig_dist));stopifnot(err<1e-8)
 pruned$node.label<-rep('',pruned$Nnode)
 ns<-split_table(pruned,kept)
 groups<-split(projected[nzchar(projected$key),],projected$key[nzchar(projected$key)])
 ns$original_edge_count<-vapply(ns$split_key,function(k)nrow(groups[[k]]),0L)
 ns$support_provenance<-ifelse(ns$original_edge_count==1,'original_558_tip_support','merged_path_support_omitted')
 ns$support<-vapply(ns$split_key,function(k){g<-groups[[k]];if(nrow(g)==1)g$support else ''},'')
 internal<-ns$child>528
 pruned$node.label[ns$child[internal]-528]<-ns$support[internal]
 lengths<-vapply(groups,function(z)sum(z$length),0.0)
 stopifnot(max(abs(ns$length-lengths[ns$split_key]))<1e-8)
 write.tree(pruned,file.path(out,'trees',paste0(kind,'.pruned30.unrooted.nwk')),digits=15)
 round<-read.tree(file.path(out,'trees',paste0(kind,'.pruned30.unrooted.nwk')))
 stopifnot(max(abs(cophenetic(round)[kept,kept]-orig_dist))<1e-8)
 ns$alphabet<-kind;maps[[kind]]<-ns
 qas[[kind]]<-data.frame(alphabet=kind,original_tips=558,removed=30,remaining=528,secondary_retained=sum(secondary%in%pruned$tip.label),max_distance_error=err,merged_internal_edges_support_omitted=sum(internal&ns$original_edge_count>1),preserved_original_support_labels=sum(internal&nzchar(ns$support)),tree_reinferred=FALSE)
}
write.table(do.call(rbind,qas),file.path(out,'pruning_QA.tsv'),sep='\t',quote=FALSE,row.names=FALSE)
write.table(do.call(rbind,maps),file.path(out,'pruned_edge_provenance.tsv'),sep='\t',quote=FALSE,row.names=FALSE)
writeLines(exclude,file.path(out,'removed_tip_ids.txt'))
writeLines(kept,file.path(out,'retained_tip_ids.txt'))
print(do.call(rbind,qas))
