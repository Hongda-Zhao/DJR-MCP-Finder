# No plotting or file writes when this helper is sourced.
descendant_tips <- function(tr) {
 n <- length(tr$tip.label); nall <- n + tr$Nnode
 children <- split(tr$edge[,2],tr$edge[,1]); memo <- vector('list',nall)
 visit <- function(v) {
  if(!is.null(memo[[v]])) return(memo[[v]])
  z <- if(v<=n) v else unlist(lapply(children[[as.character(v)]],visit),use.names=FALSE)
  memo[[v]] <<- z; z
 }
 for(v in seq_len(nall)) visit(v)
 memo
}

split_table <- function(tr, universe=sort(tr$tip.label)) {
 n <- length(universe); ds <- descendant_tips(tr)
 key <- function(v) {
  a <- sort(match(tr$tip.label[ds[[v]]],universe));b<-setdiff(seq_len(n),a)
  sa<-paste(a,collapse=',');sb<-paste(b,collapse=',')
  if(length(a)<length(b)) sa else if(length(b)<length(a)) sb else min(sa,sb)
 }
 child <- tr$edge[,2];labels<-rep('',length(child));internal<-child>length(tr$tip.label)
 if(!is.null(tr$node.label)) labels[internal]<-tr$node.label[child[internal]-length(tr$tip.label)]
 labels[is.na(labels)]<-''
 data.frame(parent=tr$edge[,1],child=child,split_key=vapply(child,key,''),length=tr$edge.length,support=labels)
}

midpoint_checked <- function(original) {
 stopifnot(!anyDuplicated(original$tip.label),all(is.finite(original$edge.length)),all(original$edge.length>=0))
 original_dist<-ape::cophenetic.phylo(original);diameter<-max(original_dist)
 if(diameter<=0)stop('Midpoint rooting requires a nonzero tree diameter.')
 anchor<-which(original_dist==diameter,arr.ind=TRUE)[1,]
 anchor_names<-rownames(original_dist)[anchor]
 tol<-1e-8*max(1,diameter)
 old<-split_table(original)
 rooted<-phangorn::midpoint(original,node.labels='delete')
 rooted<-ape::reorder.phylo(rooted,'cladewise')
 stopifnot(ape::is.rooted(rooted),setequal(rooted$tip.label,original$tip.label),all(is.finite(rooted$edge.length)),all(rooted$edge.length>=0))
 new<-split_table(rooted,sort(original$tip.label))
 stopifnot(setequal(new$split_key,old$split_key))
 # Root insertion divides an edge; compare sums for each unrooted split.
 old_length<-tapply(old$length,old$split_key,sum);new_length<-tapply(new$length,new$split_key,sum)
 split_error<-max(abs(old_length-new_length[names(old_length)]))
 new_dist<-ape::cophenetic.phylo(rooted)[rownames(original_dist),colnames(original_dist)]
 distance_error<-max(abs(original_dist-new_dist))
 depths<-ape::node.depth.edgelength(rooted)
 midpoint_error<-max(abs(depths[match(anchor_names,rooted$tip.label)]-diameter/2))
 stopifnot(split_error<tol,distance_error<tol,midpoint_error<tol)
 # Dual SH-aLRT/UFBoot labels are edge properties: remap by unrooted split,
 # rather than allowing a rerooting routine to treat them as node names.
 valid<-old[nzchar(old$support),]
 support_by_split<-lapply(split(valid$support,valid$split_key),unique)
 stopifnot(all(lengths(support_by_split)==1L))
 support_by_split<-vapply(support_by_split,function(x)x[1],'')
 rooted$node.label<-rep('',rooted$Nnode)
 new$support<-unname(support_by_split[new$split_key]);new$support[is.na(new$support)]<-''
 internal<-new$child>length(rooted$tip.label)
 rooted$node.label[new$child[internal]-length(rooted$tip.label)]<-new$support[internal]
 # The new root carries no incoming-edge support; its children may share
 # the original split's support if that edge was divided by midpoint rooting.
 represented<-unique(new$split_key[nzchar(new$support)])
 stopifnot(setequal(represented,names(support_by_split)))
 list(tree=rooted,edges=new,qa=data.frame(tips=length(rooted$tip.label),diameter=diameter,
  diameter_tip_1=anchor_names[1],diameter_tip_2=anchor_names[2],max_pairwise_distance_error=distance_error,
  max_split_length_error=split_error,midpoint_error=midpoint_error,
  supported_unrooted_splits=length(support_by_split),support_mapping='PASS'))
}

tree_geometry <- function(tr,ann,palette,class_branch_palette) {
 n<-length(tr$tip.label);alln<-n+tr$Nnode;ds<-descendant_tips(tr)
 rootnode<-setdiff(tr$edge[,1],tr$edge[,2]);stopifnot(length(rootnode)==1)
 children<-split(tr$edge[,2],tr$edge[,1]);y<-numeric(alln);tip_order<-integer()
 walk<-function(v) {
  if(v<=n) {tip_order<<-c(tip_order,v);return()}
  for(ch in children[[as.character(v)]])walk(ch)
 }
 walk(rootnode);y[tip_order]<-rev(seq_len(n))
 place<-function(v) {
  if(v<=n)return(y[v])
  z<-vapply(children[[as.character(v)]],place,0.0)
  y[v]<<-mean(range(z));y[v]
 }
 place(rootnode);x<-ape::node.depth.edgelength(tr)
 a<-ann[match(tr$tip.label,ann$tip_id),];stopifnot(identical(a$tip_id,tr$tip.label))
 outgroup<-a$biological_scope=='outgroup'
 edge<-data.frame(parent=tr$edge[,1],child=tr$edge[,2])
 edge$descendant_tips<-lengths(ds[edge$child]);edge$outgroup_only<-FALSE;edge$taxon<-'';edge$virus_class<-''
 for(k in seq_len(nrow(edge))) {
  ix<-ds[[edge$child[k]]];edge$outgroup_only[k]<-all(outgroup[ix])
  taxa<-unique(a$ref_taxon[ix])
  classes<-unique(a$virus_class[ix])
  if(!any(outgroup[ix]) && length(classes)==1)edge$virus_class[k]<-classes
  if(!any(outgroup[ix]) && length(taxa)==1)edge$taxon[k]<-taxa
 }
 edge$color_level<-ifelse(edge$outgroup_only,'outgroup',ifelse(nzchar(edge$taxon),'Order/Family',ifelse(nzchar(edge$virus_class),'Class','mixed Class')))
 edge$color<-ifelse(edge$outgroup_only,'#929292',ifelse(nzchar(edge$taxon),unname(palette[edge$taxon]),ifelse(nzchar(edge$virus_class),unname(class_branch_palette[edge$virus_class]),'#C7C7C7')))
 edge$linetype<-ifelse(edge$outgroup_only,'dashed','solid')
 stopifnot(!anyNA(edge$color),all(edge$outgroup_only[match(which(outgroup),edge$child)]))
 edge$x<-x[edge$parent];edge$xend<-x[edge$child];edge$y<-y[edge$child];edge$yend<-y[edge$child]
 geometry_error<-max(abs(edge$xend-edge$x-tr$edge.length));stopifnot(geometry_error<1e-8)
 tips<-data.frame(node=seq_len(n),tip_id=tr$tip.label,label=a$primary_official_cluster_id,taxonomy=a$ref_taxon,virus_phylum=a$virus_phylum,virus_class=a$virus_class,
  outgroup=outgroup,x=x[seq_len(n)],y=y[seq_len(n)],color=ifelse(outgroup,'#929292',unname(palette[a$ref_taxon])))
 stopifnot(!anyNA(tips$color),!anyDuplicated(tips$label),!any(grepl('^(Gold|Silver_R3)__',tips$label)))
 list(x=x,y=y,edge=edge,tips=tips,root=rootnode,geometry_error=geometry_error)
}
