suppressPackageStartupMessages(library(ape))
options(stringsAsFactors=FALSE)
b<-'outputs/Three_Phylum_pruned8_20261007';o<-'outputs/Ref_crossrank_recheck_550_20261007'
a<-read.delim(file.path(b,'annotations/Three_Phylum_annotations.tsv'),check.names=FALSE)
allrows<-list();tips<-list();ci<-0;ti<-0
for(kind in c('AA','3DI')){
 t<-read.tree(file.path(b,'trees',paste0(tolower(kind),'.pruned8.unrooted.nwk')));n<-length(t$tip.label)
 stopifnot(n==550,setequal(t$tip.label,a$tip_id));ann<-a[match(t$tip.label,a$tip_id),]
 kids<-split(t$edge[,2],t$edge[,1]);memo<-vector('list',n+t$Nnode)
 desc<-function(v){if(v<=n)return(v);if(!is.null(memo[[v]]))return(memo[[v]]);z<-unlist(lapply(kids[[as.character(v)]],desc));memo[[v]]<<-z;z}
 sides<-list();si<-0
 for(e in seq_len(nrow(t$edge))){v<-t$edge[e,2];if(v<=n)next
  s<-desc(v);sp<-suppressWarnings(as.numeric(strsplit(t$node.label[v-n],'/',fixed=TRUE)[[1]]));if(length(sp)!=2)sp<-c(NA_real_,NA_real_)
  for(side in list(s,setdiff(seq_len(n),s))){if(length(side)<3||length(side)>n-3)next;si<-si+1;sides[[si]]<-list(tips=side,sh=sp[1],uf=sp[2],edge=e)}
 }
 d<-cophenetic(t)[t$tip.label,t$tip.label];te<-t;te$edge.length[]<-1;de<-cophenetic(te)[t$tip.label,t$tip.label]
 for(rank in c('Phylum','Class')){
  labs<-ann[[if(rank=='Phylum')'virus_phylum' else 'virus_class']];stopifnot(!anyNA(labs),all(nzchar(labs)));sz<-table(labs)
  for(j in seq_len(n)){
   nn<-function(mat){dd<-mat[j,];dd[j]<-Inf;k<-sort(dd)[5];ix<-which(dd<=k+1e-10);tb<-sort(table(labs[ix]),decreasing=TRUE);near<-which(dd<=min(dd)+1e-10);list(ids=paste(t$tip.label[ix],collapse=';'),n=length(ix),alt=names(tb)[1],frac=as.numeric(tb[1])/length(ix),own=mean(labs[ix]==labs[j]),nearest=paste(t$tip.label[near],collapse=';'),nearest_labels=paste(unique(labs[near]),collapse=';'))}
   np<-nn(d);ne<-nn(de);same<-which(labs==labs[j]&seq_len(n)!=j);other<-which(labs!=labs[j])
   ti<-ti+1;tips[[ti]]<-data.frame(tree=kind,rank=rank,tip_id=t$tip.label[j],own_group=labs[j],group_n=as.integer(sz[[labs[j]]]),terminal_length=t$edge.length[match(j,t$edge[,2])],nearest_same_distance=if(length(same))min(d[j,same])else NA,nearest_foreign_distance=min(d[j,other]),pat_alt=np$alt,pat_frac=np$frac,pat_own=np$own,edge_alt=ne$alt,edge_frac=ne$frac,edge_own=ne$own,pat_neighbors=np$ids,edge_neighbors=ne$ids,pat_nearest=np$nearest,edge_nearest=ne$nearest,pat_nearest_groups=np$nearest_labels,edge_nearest_groups=ne$nearest_labels)
  }
  for(s in sides){tb<-sort(table(labs[s$tips]),decreasing=TRUE);alt<-names(tb)[1];nalt<-as.integer(tb[1]);minor<-s$tips[labs[s$tips]!=alt];if(!length(minor))next
   pure_single<-length(minor)==1 && length(s$tips)>=3
   broad<-nalt/length(s$tips)>=.8
   if(!pure_single&&!broad)next
   for(j in minor){ownn<-sum(labs[s$tips]==labs[j]);if(ownn>2)next
    ci<-ci+1;allrows[[ci]]<-data.frame(tree=kind,rank=rank,tip_id=t$tip.label[j],own_group=labs[j],group_n=as.integer(sz[[labs[j]]]),alternative=alt,side_n=length(s$tips),own_n=ownn,foreign_n=nalt,foreign_fraction=nalt/length(s$tips),pure_singleton=pure_single,SH=s$sh,UF=s$uf,strong=!anyNA(c(s$sh,s$uf))&&s$sh>=80&&s$uf>=95,edge=s$edge,members=paste(t$tip.label[s$tips],collapse=';'))
   }
  }
 }
}
w<-function(x,p)write.table(do.call(rbind,x),file.path(o,p),sep='\t',quote=FALSE,row.names=FALSE,na='')
w(tips,'all_tip_neighborhoods.tsv');w(allrows,'all_foreign_sides.tsv')
cat('Neighborhood rows',ti,'candidate sides',ci,'\n')
