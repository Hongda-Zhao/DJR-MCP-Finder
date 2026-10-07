#!/usr/bin/env Rscript
options(stringsAsFactors=FALSE,warn=1,expressions=50000)
rawargs<-commandArgs(FALSE);script_dir<-dirname(normalizePath(sub('^--file=','',rawargs[grepl('^--file=',rawargs)])))
cli<-commandArgs(TRUE)
arg<-function(name,default) {i<-match(name,cli);if(is.na(i))return(default);if(i==length(cli))stop('Missing value: ',name);cli[i+1L]}
if('--help'%in%cli){cat('Rscript render_three_phylum_midpoint.R [--project PATH] [--annotations PATH] [--out PATH] [--branch-width 0.55] [--check-only]\n');quit(status=0)}
needed<-c('ape','phangorn','ggplot2','patchwork');missing<-needed[!vapply(needed,requireNamespace,TRUE,quietly=TRUE)]
if(length(missing))stop('Install required packages: ',paste(missing,collapse=', '))
suppressPackageStartupMessages({library(ape);library(ggplot2);library(patchwork)})
source(file.path(script_dir,'tree_helpers.R'))
project<-arg('--project',normalizePath(file.path(script_dir,'..')))
annotation_dir<-arg('--annotations',file.path(project,'annotations'));out<-arg('--out',file.path(script_dir,'figures_latest'))
bw<-as.numeric(arg('--branch-width','0.55'));stopifnot(is.finite(bw),bw>0)
check_only<-'--check-only'%in%cli
if(check_only)options(device=function(...)grDevices::pdf(file=NULL))
if(!check_only){dir.create(out,recursive=TRUE,showWarnings=FALSE);dir.create(file.path(out,'rooted_trees'),showWarnings=FALSE)}
phylum<-'Three_Phylum'
ann<-setNames(lapply(phylum,function(p)read.delim(file.path(annotation_dir,paste0(p,'_annotations.tsv')),quote='',check.names=FALSE,colClasses='character')),phylum)
# Lengths come from the original, unaligned proteins, not AA/3Di alignment width.
faa_file<-file.path(project,'inputs','Three_Phylum','reference.faa')
faa_lines<-trimws(readLines(faa_file,warn=FALSE));faa_lines<-faa_lines[nzchar(faa_lines)]
headers<-which(startsWith(faa_lines,'>'))
stopifnot(length(headers)==528,headers[1]==1)
faa_ids<-sub(' .*$', '',substring(faa_lines[headers],2))
ends<-c(headers[-1]-1L,length(faa_lines))
faa_sequences<-vapply(seq_along(headers),function(i){stopifnot(ends[i]>headers[i]);toupper(paste0(faa_lines[seq.int(headers[i]+1L,ends[i])],collapse=''))},'')
stopifnot(!anyDuplicated(faa_ids),all(grepl('^[A-Z]+$',faa_sequences)))
faa_lengths<-setNames(nchar(faa_sequences),faa_ids)
sequence_meta<-read.delim(file.path(project,'inputs','Three_Phylum','sequence_metadata.tsv'),quote='',colClasses='character')
stopifnot(!anyDuplicated(sequence_meta$tip_id),setequal(sequence_meta$tip_id,faa_ids),all(faa_lengths[sequence_meta$tip_id]==as.integer(sequence_meta$length_aa)))
for(ph in phylum){d<-ann[[ph]];stopifnot(setequal(d$tip_id,faa_ids));d$faa_length_aa<-unname(faa_lengths[d$tip_id]);ann[[ph]]<-d}
length_limit<-ceiling(max(faa_lengths)/1000)*1000
length_ticks<-seq(0,length_limit,length.out=4)
length_color<-'#586675';length_ring_width<-.32
taxa<-sort(unique(unlist(lapply(ann,function(d)d$ref_taxon[d$biological_scope!='outgroup']))))
tax_scheme<-read.delim(file.path(annotation_dir,'taxonomy_color_scheme.tsv'),quote='',comment.char='',colClasses='character')
stopifnot(!anyDuplicated(tax_scheme$taxon),all(taxa%in%tax_scheme$taxon),all(grepl('^#[0-9A-Fa-f]{6}$',tax_scheme$color)))
palette<-setNames(tax_scheme$color,tax_scheme$taxon)
stopifnot(nrow(ann[[1]])==528,all(ann[[1]]$biological_scope=='ingroup'))
expected_counts<-c(Nucleocytoviricota=392,Preplasmiviricota=112,Produgelaviricota=24)
observed_counts<-table(ann[[1]]$virus_phylum)
stopifnot(setequal(names(observed_counts),names(expected_counts)),all(observed_counts[names(expected_counts)]==expected_counts))
# Fixed categorical palette, grouped by phylum in the legend.
# Phylum families: blue/cyan/green, orange/red/pink, gray/black.
class_scheme<-read.delim(file.path(annotation_dir,'class_color_scheme.tsv'),quote='',comment.char='',colClasses='character')
stopifnot(!anyDuplicated(class_scheme$virus_class),!anyNA(class_scheme),all(grepl('^#[0-9A-Fa-f]{6}$',class_scheme$color)))
for(d in ann) {
 stopifnot(all(c('virus_class','virus_phylum')%in%names(d)),!anyNA(d$virus_class),all(nzchar(d$virus_class)))
 ix<-match(d$virus_class,class_scheme$virus_class)
 stopifnot(!anyNA(ix),all(d$virus_phylum==class_scheme$virus_phylum[ix]))
}
class_palette<-setNames(class_scheme$color,class_scheme$virus_class)
class_branch_palette<-setNames(class_scheme$branch_color,class_scheme$virus_class)
for(d in ann) {
 ix<-match(d$ref_taxon,tax_scheme$taxon)
 stopifnot(!anyNA(ix),all(d$virus_class==tax_scheme$virus_class[ix]),all(d$virus_phylum==tax_scheme$virus_phylum[ix]))
}
stopifnot(all(tax_scheme$class_color==class_palette[tax_scheme$virus_class]))
context_scheme<-read.delim(file.path(annotation_dir,'context_color_scheme.tsv'),quote='',comment.char='',colClasses='character')
context_palette<-setNames(context_scheme$color,context_scheme$context_group)
stopifnot(!anyDuplicated(context_scheme$context_group),all(grepl('^#[0-9A-Fa-f]{6}$',context_scheme$color)))
for(d in ann) {
 stopifnot(all(c('context_group','context_kind','context_label','host_kingdom_group','source_kind_display')%in%names(d)),!anyNA(d$context_group),!anyNA(d$context_kind))
 stopifnot(all(d$context_group[nzchar(d$context_group)]%in%names(context_palette)))
 stopifnot(all(!nzchar(d$host_kingdom_group[d$source_kind_display=='Environmental'])))
}
write_tsv<-function(x,name)write.table(x,file.path(out,name),sep='\t',row.names=FALSE,quote=FALSE,na='')
theme_set(theme_void(base_family='sans',base_size=10))
export_pdf<-function(p,stem,w,h) {
 ggsave(paste0(stem,'.pdf'),p,width=w,height=h,units='in',device=cairo_pdf,bg='white',limitsize=FALSE)
}
legend_for<-function(d,with_context=TRUE) {
 entries<-list();y<-0
 add<-function(type,label,color='#333333') {
  y<<-y-1
  entries[[length(entries)+1L]]<<-data.frame(type=type,y=y,label=label,color=color)
 }
 add('phylum','Outermost bars: protein length')
 add('context',paste0('Original FAA: ',min(faa_lengths),' - ',max(faa_lengths),' aa'),length_color)
 add('heading',paste0('Linear scale: 0 - ',length_limit,' aa; shared AA / 3Di'))
 for(ph in unique(class_scheme$virus_phylum)) {
  add('phylum',ph)
  for(cl in class_scheme$virus_class[class_scheme$virus_phylum==ph]) {
   subset<-d[d$virus_class==cl,]
   if(!nrow(subset))next
   add('class',paste0(cl,'  [',nrow(subset),']'),unname(class_palette[cl]))
   for(taxon in sort(unique(subset$ref_taxon)))add('taxon',paste0(taxon,'  [',sum(subset$ref_taxon==taxon),']'),unname(palette[taxon]))
  }
  y<-y-.65
 }
 add('mixed','Mixed-Class internal branch','#C7C7C7')
 if(with_context) {
 add('phylum','Separate annotation rings')
 for(kind in c('Host','Environment')) {
  add('heading',if(kind=='Host')'Ring 2: Host broad group' else 'Ring 3: MetaVR environment')
  for(key in context_scheme$context_group[context_scheme$kind==kind]) {
   count<-sum(d$context_group==key)
   if(count)add('context',paste0(sub('^(Host|Env): ','',key),'  [',count,']'),unname(context_palette[key]))
  }
 }
 }
 z<-do.call(rbind,entries)
 ggplot()+
 geom_text(data=z[z$type=='phylum',],aes(x=0,y=y,label=label),hjust=0,size=3.2,fontface='bold',color='#222222')+
 geom_text(data=z[z$type=='heading',],aes(x=.1,y=y,label=label),hjust=0,size=3,fontface='bold',color='#555555')+
 geom_tile(data=z[z$type=='context',],aes(x=.16,y=y,fill=color),width=.32,height=.52)+
 geom_text(data=z[z$type=='context',],aes(x=.43,y=y,label=label),hjust=0,size=2.95,color='#333333')+
 geom_tile(data=z[z$type=='class',],aes(x=.16,y=y,fill=color),width=.32,height=.52)+
 geom_text(data=z[z$type=='class',],aes(x=.43,y=y,label=label),hjust=0,size=3.05,fontface='bold',color='#333333')+
 geom_segment(data=z[z$type%in%c('taxon','mixed'),],aes(x=.35,xend=.95,y=y,yend=y,color=color),linewidth=bw+.2)+
 geom_text(data=z[z$type%in%c('taxon','mixed'),],aes(x=1.12,y=y,label=label),hjust=0,size=2.95,color='#333333')+
 scale_color_identity()+scale_fill_identity()+
 annotate('text',x=0,y=.8,label='Class / related Order-Family shades',hjust=0,fontface='bold',size=3.7)+
 annotate('text',x=0,y=y-1.2,label=if(with_context)'Inside to outside: Class / Host / Environment / Length.\nBlank: no annotation. 528 retained tips; 30 candidates (8 prior + 22 current) pruned.\nEnvironment is sampling context, not virus host.\nLength bars share a zero baseline; original FAA residues.' else 'Inside to outside: Class / Length.\nHost and Environment layers omitted; 528 tips retained after pruning 30 candidates (8 prior + 22 current).\nLength bars share a zero baseline; original FAA residues.',hjust=0,vjust=1,size=2.6,color='#666666')+
 coord_cartesian(xlim=c(0,8.8),ylim=c(y-5,.9),clip='off')+theme_void()+theme(plot.margin=margin(4,18,4,0))
}
circles<-list();legends<-list();qa<-list();edge_tables<-list();tip_tables<-list()
variants<-'taxonomy_only'
for(ph in phylum)for(alphabet in c('aa','3di')) {
 id<-paste(ph,toupper(alphabet),sep='_');message(if(check_only)'Checking ' else 'Rendering ',id)
 tree_file<-file.path(project,'trees',paste0(alphabet,'.pruned30.unrooted.nwk'))
 stopifnot(file.exists(file.path(project,'pruning_QA.tsv')))
 original<-read.tree(tree_file);d<-ann[[ph]]
 stopifnot(!anyDuplicated(d$tip_id),setequal(original$tip.label,d$tip_id))
 result<-midpoint_checked(original);tr<-result$tree;g<-tree_geometry(tr,d,palette,class_branch_palette);n<-length(tr$tip.label);E<-g$edge;T<-g$tips;R<-max(g$x)
 T$class_color<-unname(class_palette[T$virus_class]);stopifnot(!anyNA(T$class_color))
 ix<-match(T$tip_id,d$tip_id)
 T$context_group<-d$context_group[ix];T$context_label<-d$context_label[ix]
 T$context_kind<-d$context_kind[ix]
 T$faa_length_aa<-d$faa_length_aa[ix]
 stopifnot(all(T$faa_length_aa==faa_lengths[T$tip_id]))
 T$host_kingdom_group<-d$host_kingdom_group[ix];T$environment_detail<-d$environment_detail[ix]
 T$context_color<-unname(context_palette[T$context_group])
 stopifnot(all(is.na(T$context_color)==!nzchar(T$context_group)))
 H<-T[T$context_kind=='Host',,drop=FALSE];V<-T[T$context_kind=='Environment',,drop=FALSE]
 stopifnot(nrow(H)==54,nrow(V)==413,!any(H$tip_id%in%V$tip_id))
 labels<-result$edges$support[match(E$child,result$edges$child)]
 E$support<-labels;E$split_key<-result$edges$split_key[match(E$child,result$edges$child)]
 strong<-which(vapply(strsplit(labels,'/',fixed=TRUE),function(s)length(s)==2 && all(is.finite(suppressWarnings(as.numeric(s)))) && as.numeric(s[1])>=80 && as.numeric(s[2])>=95,TRUE))
 dotnodes<-E$child[strong]
 result$qa$tree<-id;result$qa$outgroup_tips<-sum(T$outgroup);result$qa$pure_outgroup_edges<-sum(E$outgroup_only);result$qa$max_display_geometry_error<-g$geometry_error
 qa[[id]]<-result$qa;E$tree<-id;edge_tables[[id]]<-E;T$tree<-id;tip_tables[[id]]<-T
 qa[[id]]$host_tips<-nrow(H);qa[[id]]$environment_tips<-nrow(V);qa[[id]]$blank_context_tips<-sum(!nzchar(T$context_group))
 qa[[id]]$length_bars<-nrow(T);qa[[id]]$min_length_aa<-min(T$faa_length_aa);qa[[id]]$max_length_aa<-max(T$faa_length_aa);qa[[id]]$length_scale_max_aa<-length_limit
 if(!check_only)write.tree(tr,file.path(out,'rooted_trees',paste0(id,'.midpoint.nwk')),digits=15)
 units<-if(alphabet=='aa')'AA substitutions/site' else '3Di substitutions/site'
 report<-readLines(file.path('/Users/zhaohongda/Documents/DJR-MCP Finder/outputs/Three_Phylum_RefOnly_FoldMason_IQTREE_20260924','iqtree',ph,alphabet,'reference.iqtree'),warn=FALSE)
 model<-sub('Best-fit model according to BIC: ','',report[grepl('Best-fit model according to BIC:',report)][1])
 for(variant in variants) {
 with_context<-variant=='with_host_environment'
 # Same branch style drives both layouts. Connecting arcs/vertical arms
 # inherit the style of the child edge; mixed descendant sets stay neutral.
 angle<-2*pi*(g$y-.5)/n
 radial<-transform(E,x=g$x[parent]*cos(angle[child]),y=g$x[parent]*sin(angle[child]),xend=g$x[child]*cos(angle[child]),yend=g$x[child]*sin(angle[child]))
 arcs<-do.call(rbind,lapply(seq_len(nrow(E)),function(k) {
  a<-seq(angle[E$parent[k]],angle[E$child[k]],length.out=max(2,ceiling(abs(angle[E$parent[k]]-angle[E$child[k]])*60)))
  data.frame(x=g$x[E$parent[k]]*cos(a),y=g$x[E$parent[k]]*sin(a),edge=k,color=E$color[k],linetype=E$linetype[k])
 }))
 ring_start<-R*1.035;ring_end<-R*1.06
 ring<-do.call(rbind,lapply(seq_len(n),function(i){a<-angle[i]+c(-.49,.49)*2*pi/n;data.frame(x=c(ring_start*cos(a),rev(ring_end*cos(a))),y=c(ring_start*sin(a),rev(ring_end*sin(a))),group=i,color=T$class_color[i])}))
 make_ring<-function(kind,start,end) {
  selected<-which(T$context_kind==kind & with_context)
  if(!length(selected))return(data.frame(x=numeric(),y=numeric(),group=integer(),color=character()))
  do.call(rbind,lapply(selected,function(i){a<-angle[i]+c(-.49,.49)*2*pi/n;data.frame(x=c(R*start*cos(a),rev(R*end*cos(a))),y=c(R*start*sin(a),rev(R*end*sin(a))),group=i,color=T$context_color[i])}))
 }
 host_ring<-make_ring('Host',1.077,1.112)
 environment_ring<-make_ring('Environment',1.129,1.164)
 stopifnot(length(unique(host_ring$group))==if(with_context)nrow(H) else 0L,
           length(unique(environment_ring$group))==if(with_context)nrow(V) else 0L)
 length_start<-R*if(with_context)1.20 else 1.10
 length_ends<-length_start+R*length_ring_width*T$faa_length_aa/length_limit
 length_bars<-do.call(rbind,lapply(seq_len(n),function(i){a<-angle[i]+c(-.40,.40)*2*pi/n;data.frame(x=c(length_start*cos(a),rev(length_ends[i]*cos(a))),y=c(length_start*sin(a),rev(length_ends[i]*sin(a))),group=i)}))
 stopifnot(length(unique(length_bars$group))==n,all(length_ends>length_start),max(abs((length_ends-length_start)/(R*length_ring_width)*length_limit-T$faa_length_aa))<1e-9)
 length_grid<-do.call(rbind,lapply(length_ticks,function(tick){a<-seq(0,2*pi,length.out=720);radius<-length_start+R*length_ring_width*tick/length_limit;data.frame(x=radius*cos(a),y=radius*sin(a),tick=tick)}))
 length_axis<-data.frame(x=R*.3+R*length_ring_width*length_ticks/length_limit,label=as.character(length_ticks))
 guides<-data.frame(x=g$x[seq_len(n)]*cos(angle[seq_len(n)]),y=g$x[seq_len(n)]*sin(angle[seq_len(n)]),xend=ring_start*cos(angle[seq_len(n)]),yend=ring_start*sin(angle[seq_len(n)]))
 dots<-data.frame(x=g$x[dotnodes]*cos(angle[dotnodes]),y=g$x[dotnodes]*sin(angle[dotnodes]))
 scale_candidates<-pretty(c(0,R*.25),n=2);sw<-max(scale_candidates[scale_candidates>0 & scale_candidates<R*.4]);if(!is.finite(sw))sw<-R*.2
 circular<-ggplot()+geom_segment(data=guides,aes(x=x,y=y,xend=xend,yend=yend),color='#ECECEC',linewidth=.10)+
 geom_path(data=arcs,aes(x=x,y=y,group=edge,color=color,linetype=linetype),linewidth=bw,lineend='round')+
 geom_segment(data=radial,aes(x=x,y=y,xend=xend,yend=yend,color=color,linetype=linetype),linewidth=bw,lineend='round')+
 geom_point(data=dots,aes(x=x,y=y),size=.60,color='#222222')+geom_polygon(data=ring,aes(x=x,y=y,group=group,fill=color),color=NA)+
 geom_polygon(data=host_ring,aes(x=x,y=y,group=group,fill=color),color=NA)+
 geom_polygon(data=environment_ring,aes(x=x,y=y,group=group,fill=color),color=NA)+
 geom_path(data=length_grid,aes(x=x,y=y,group=tick),color='#D8DDE2',linewidth=.12)+
 geom_polygon(data=length_bars,aes(x=x,y=y,group=group),fill=length_color,color=NA)+scale_color_identity()+scale_linetype_identity()+scale_fill_identity()+
 annotate('segment',x=-R*.9,xend=-R*.9+sw,y=-R*1.65,yend=-R*1.65,linewidth=.6)+annotate('text',x=-R*.9+sw/2,y=-R*1.73,label=paste(format(sw),units),size=3)+
 annotate('segment',x=R*.3,xend=R*(.3+length_ring_width),y=-R*1.65,yend=-R*1.65,linewidth=.6,color=length_color)+
 geom_segment(data=length_axis,aes(x=x,xend=x),y=-R*1.65,yend=-R*1.67,linewidth=.35,color=length_color)+
 geom_text(data=length_axis,aes(x=x,label=label),y=-R*1.71,size=2.5,color=length_color)+
 annotate('text',x=R*(.3+length_ring_width/2),y=-R*1.79,label='FAA length (aa)',size=3,color=length_color)+
 coord_equal(xlim=c(-R*1.58,R*1.58),ylim=c(-R*1.85,R*1.58),expand=FALSE)+theme_void()
 leg<-legend_for(d,with_context);circles[[paste(id,variant,sep='_')]]<-circular;legends[[paste(ph,variant,sep='_')]]<-leg
 cap<-paste('Midpoint root: centre of the longest tip-to-tip path; not an independently validated biological root.',
  'Branches: Order / Family shades linked to Class ring colours. Same-Class ancestral branches: Class tone. Mixed-Class branches: grey.',
  if(with_context)'Rings/strips, inside to outside: Class / Host / Environment. Missing annotations are blank; 30 tips pruned in total (8 prior + 22 current); exploratory display.' else 'Class ring/strip retained. Host and Environment annotations omitted; 30 tips pruned in total (8 prior + 22 current); exploratory display.',
  if(with_context)'Env means sampling environment, including organism-associated samples; it does not assert a virus-host relationship.' else NULL,
  paste0('Outermost bars: original, unaligned FAA protein length (aa); zero-based linear scale 0-',length_limit,' shared by AA and 3Di.'),
  'Black dots: original 558-tip SH-aLRT >=80 and UFBoot >=95; not recalculated. Support on merged paths omitted.
Retained pairwise distances are unchanged. This is pruning for display, not new phylogenetic inference.',sep='\n')
 # Full rectangular tree, on one large PDF page with every tip label.
 vertical<-transform(E,x=g$x[parent],xend=g$x[parent],y=g$y[parent],yend=g$y[child])
 ndots<-data.frame(x=g$x[dotnodes],y=g$y[dotnodes])
 rect<-ggplot()+geom_segment(data=vertical,aes(x=x,y=y,xend=xend,yend=yend,color=color,linetype=linetype),linewidth=bw,lineend='round')+
 geom_segment(data=E,aes(x=x,y=y,xend=xend,yend=yend,color=color,linetype=linetype),linewidth=bw,lineend='round')+
 geom_point(data=ndots,aes(x=x,y=y),size=.65,color='#222222')+scale_color_identity()+scale_linetype_identity()+scale_fill_identity()+
 scale_x_continuous(breaks=pretty(c(0,R),n=5)[pretty(c(0,R),n=5)<=R],expand=c(0,0))+
 theme_classic(base_family='sans')+theme(axis.line.y=element_blank(),axis.ticks.y=element_blank(),axis.text.y=element_blank(),axis.title.y=element_blank(),axis.text.x=element_text(size=8),axis.title.x=element_text(size=9),plot.title=element_text(size=14,face='bold'),plot.subtitle=element_text(size=9),plot.caption=element_text(size=8,hjust=0),plot.margin=margin(12,14,12,12),legend.position='none')+labs(x=units)
 labelx<-R*1.18;taxx<-R*1.93;classx<-R*2.63;hostx<-R*3.22;envx<-R*3.68;endx<-R*5.22
 if(!with_context){labelx<-R*1.08;taxx<-R*1.83;classx<-R*2.53;endx<-R*3.12}
 lengthx<-endx+R*.06;lengthwidth<-R*.55;endx<-lengthx+R*.85
 T$length_bar_end<-lengthx+lengthwidth*T$faa_length_aa/length_limit
 rect_length_axis<-data.frame(x=lengthx+lengthwidth*length_ticks/length_limit,label=as.character(length_ticks))
 add_class_strip<-function(p,tips) p+geom_rect(data=tips,aes(xmin=R*1.025,xmax=R*1.05,ymin=y-.43,ymax=y+.43,fill=class_color),color=NA)
 add_labels<-function(p,tips) {
  add_class_strip(p+geom_segment(data=tips,aes(x=x,xend=R*1.02,y=y,yend=y),color='#DEDEDE',linewidth=.13),tips)+
  geom_rect(data=H[rep(with_context,nrow(H)),,drop=FALSE],aes(xmin=R*1.065,xmax=R*1.10,ymin=y-.43,ymax=y+.43,fill=context_color),color=NA)+
  geom_rect(data=V[rep(with_context,nrow(V)),,drop=FALSE],aes(xmin=R*1.115,xmax=R*1.15,ymin=y-.43,ymax=y+.43,fill=context_color),color=NA)+
  geom_text(data=tips,aes(x=labelx,y=y,label=label,color=color),hjust=0,size=2.9,family='sans')+
  geom_text(data=tips,aes(x=taxx,y=y,label=taxonomy,color=color),hjust=0,size=2.75,family='sans')+
  geom_text(data=tips,aes(x=classx,y=y,label=virus_class),color='#333333',hjust=0,size=2.75,family='sans')+
  geom_text(data=H[rep(with_context,nrow(H)),,drop=FALSE],aes(x=hostx,y=y,label=host_kingdom_group),color='#333333',hjust=0,size=2.75,family='sans')+
  geom_text(data=V[rep(with_context,nrow(V)),,drop=FALSE],aes(x=envx,y=y,label=context_label),color='#333333',hjust=0,size=2.75,family='sans')
 }
 full<-add_labels(rect,T)+
 geom_rect(data=T,aes(xmin=lengthx,xmax=length_bar_end,ymin=y-.35,ymax=y+.35),fill=length_color,color=NA)+
 geom_text(data=T,aes(y=y,label=faa_length_aa),x=lengthx+R*.60,hjust=0,size=2.6,color=length_color)+
 annotate('segment',x=lengthx,xend=lengthx+lengthwidth,y=n+1.1,yend=n+1.1,linewidth=.3,color=length_color)+
 geom_segment(data=rect_length_axis,aes(x=x,xend=x),y=n+1.1,yend=n+1.4,linewidth=.3,color=length_color)+
 geom_text(data=rect_length_axis,aes(x=x,label=label),y=n+2.1,size=2.6,color=length_color)+
 annotate('text',x=lengthx+lengthwidth/2,y=n+3.3,label='FAA length (aa)',size=2.9,color=length_color)+
 coord_cartesian(xlim=c(0,endx),ylim=c(.4,n+4.5),expand=FALSE,clip='on')+
 labs(title=paste0('Three phyla', ' | ',toupper(alphabet),' | 30-tip pruned display (not re-inferred)'),subtitle=paste0(n,' retained references | Original model: ',model,' | Columns: Reference cluster ID / Order or Family / Class',if(with_context)' / Host / Environment' else '',' / FAA length (aa)'),caption=cap)
 fullheight<-max(12,n*.155+2)
 if(check_only) {
  ggplot_build(leg);ggplot_build(circular);ggplot_build(full)
  message('  PASS: ',variant,' | Host ring: ',length(unique(host_ring$group)),' | Environment ring: ',length(unique(environment_ring$group)),' | FAA bars: ',length(unique(length_bars$group)))
  next
 }
 export_pdf(full,file.path(out,paste0(id,'_midpoint_rectangular_full_',variant)),if(with_context)32 else 21,fullheight)
 }
}
for(ph in phylum)for(variant in variants) {
 with_context<-variant=='with_host_environment'
 comparison<-(circles[[paste(ph,'AA',variant,sep='_')]]+circles[[paste(ph,'3DI',variant,sep='_')]]+legends[[paste(ph,variant,sep='_')]]+plot_layout(widths=c(1,1,.85)))+
 plot_annotation(title='Three phyla | 30 tips pruned (8 prior + 22 current) | 528 retained references',subtitle=paste('Left: AA | Centre: 3Di | Separate tree-distance scales; shared FAA-length scale |',if(with_context)'Class / Host / Environment / Length' else 'Class / Length'),caption=paste0('Branches: related Order / Family shades. ',if(with_context)'Annotation rings: Class / Host / Environment. Missing annotations are blank. Environment is sampling context, not virus host.' else 'Class ring retained. Host and Environment rings and legends omitted.', '\nOutermost bars: original FAA length, linear 0-',length_limit,' aa. Display pruning only; topology and support not re-inferred. Dots retain original support on unmerged edges. Midpoint root assumed.'),theme=theme(plot.title=element_text(size=17,face='bold'),plot.subtitle=element_text(size=10),plot.caption=element_text(size=8,hjust=0),plot.margin=margin(12,12,12,12)))
 if(check_only){patchwork::patchworkGrob(comparison);message('  PASS: comparison assembly ',variant)} else {export_pdf(comparison,file.path(out,paste0(ph,'_AA_3Di_midpoint_comparison_',variant)),30,18);ggsave(file.path(out,'AA_3Di_pruned30_overview.png'),comparison,width=20,height=12,units='in',dpi=150,bg='white',limitsize=FALSE)}
}
if(check_only) {print(do.call(rbind,qa));message('PASS: rooting, distances, splits, support, separate annotation rings, both variants and comparison assemblies. No figures or output files written.');quit(status=0)}
write_tsv(do.call(rbind,qa),'midpoint_QA.tsv');write_tsv(do.call(rbind,edge_tables),'rooted_edge_annotations.tsv');write_tsv(do.call(rbind,tip_tables),'tip_display_labels.tsv')
write_tsv(data.frame(taxon=names(palette),color=unname(palette)),'taxonomy_palette.tsv')
write_tsv(class_scheme,'class_palette.tsv')
write_tsv(context_scheme,'context_palette.tsv')
write_tsv(data.frame(tip_id=names(faa_lengths),faa_length_aa=unname(faa_lengths)),'faa_lengths.tsv')
write_tsv(data.frame(unit='aa',minimum=0,maximum=length_limit,transform='linear',source='inputs/Three_Phylum/reference.faa'),'faa_length_scale.tsv')
writeLines(capture.output(sessionInfo()),file.path(out,'R_sessionInfo.txt'))
message('DONE: ',normalizePath(out))
