suppressPackageStartupMessages(library(ape));options(stringsAsFactors=FALSE)
b<-'outputs/Three_Phylum_pruned8_20261007';o<-'outputs/Ref_crossrank_recheck_550_20261007'
a<-read.delim(file.path(b,'annotations/Three_Phylum_annotations.tsv'));cand<-unique(read.delim(file.path(o,'all_foreign_sides.tsv'))$tip_id)
out<-list();k<-0
for(kind in c('AA','3DI')){
 t<-read.tree(file.path(b,'trees',paste0(tolower(kind),'.pruned8.unrooted.nwk')));n<-length(t$tip.label);ann<-a[match(t$tip.label,a$tip_id),]
 adj<-vector('list',n+t$Nnode)
 for(i in seq_len(nrow(t$edge))){u<-t$edge[i,1];v<-t$edge[i,2];adj[[u]]<-c(adj[[u]],v);adj[[v]]<-c(adj[[v]],u)}
 walk<-function(v,parent){if(v<=n)return(data.frame(tip=v,edges=0L));x<-do.call(rbind,lapply(setdiff(adj[[v]],parent),function(w)walk(w,v)));x$edges<-x$edges+1L;x}
 for(id in cand){j<-match(id,t$tip.label);v<-adj[[j]][1]
  for(w in setdiff(adj[[v]],j)){
   z<-walk(w,v);near<-z$tip[z$edges==min(z$edges)]
   edge<-which((t$edge[,1]==v&t$edge[,2]==w)|(t$edge[,1]==w&t$edge[,2]==v));child<-t$edge[edge,2];support<-if(child>n)t$node.label[child-n]else''
   for(rank in c('Class','Phylum')){labs<-ann[[if(rank=='Class')'virus_class'else'virus_phylum']];tb<-sort(table(labs[z$tip]),decreasing=TRUE);tn<-sort(table(labs[near]),decreasing=TRUE)
    k<-k+1;out[[k]]<-data.frame(tree=kind,rank=rank,tip_id=id,arm_size=nrow(z),arm_dominant=names(tb)[1],arm_fraction=as.numeric(tb[1])/nrow(z),arm_support=support,nearest_edges=min(z$edges)+1L,nearest_n=length(near),nearest_dominant=names(tn)[1],nearest_fraction=as.numeric(tn[1])/length(near),nearest_groups=paste(names(tn),collapse=';'),nearest_ids=paste(t$tip.label[near],collapse=';'),all_members=paste(t$tip.label[z$tip],collapse=';'))
   }
  }
 }
}
write.table(do.call(rbind,out),file.path(o,'attachment_arms.tsv'),sep='\t',quote=FALSE,row.names=FALSE)
