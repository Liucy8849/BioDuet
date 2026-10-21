# Independent reference entry: never imports the candidate script or its output.
# Uses private truth design, its own model matrix, and the same specified statistics library.
argv <- commandArgs(trailingOnly=TRUE)
stopifnot(length(argv)==4L)
stopifnot(as.character(utils::packageVersion("edgeR"))==argv[[4]])
meta <- utils::read.delim(argv[[2]],check.names=FALSE,stringsAsFactors=FALSE)
stopifnot(identical(names(meta),c("library_id","donor_id","condition")))
stopifnot(!anyDuplicated(meta$library_id),all(meta$condition %in% c("control","stim")))
donors <- sort(unique(meta$donor_id))
stopifnot(length(donors)>=2L,all(table(meta$donor_id,meta$condition)==1L))
raw <- utils::read.delim(argv[[1]],check.names=FALSE,row.names=1)
stopifnot(setequal(colnames(raw),meta$library_id))
# Baseline donor intercepts plus a within-donor treatment indicator.
blocked <- sapply(donors,function(id) as.numeric(meta$donor_id==id))
colnames(blocked) <- paste0("donor_",seq_along(donors))
# Canonical treatment coding of the specified ~ donor + condition model.
# Construct independently, but use the same coefficient basis to avoid
# implementation-dependent convergence differences between equivalent bases.
X <- cbind(intercept=1,blocked[,-1,drop=FALSE],stimulus=as.numeric(meta$condition=="stim"))
stopifnot(qr(X)$rank==ncol(X))
obj <- edgeR::DGEList(as.matrix(raw[,meta$library_id,drop=FALSE]))
accepted <- edgeR::filterByExpr(obj,design=X,min.count=10,min.total.count=15,large.n=10,min.prop=0.7)
stopifnot(sum(accepted)>=2)
obj <- obj[accepted,,keep.lib.sizes=FALSE]
obj <- edgeR::calcNormFactors(obj,method="TMM")
obj <- edgeR::estimateDisp(obj,X,robust=FALSE)
model <- edgeR::glmQLFit(obj,X,robust=FALSE,legacy=TRUE)
comparison <- edgeR::glmQLFTest(model,coef=ncol(X))
table <- comparison$table
table$FDR <- p.adjust(table$PValue,method="BH")
utils::write.table(data.frame(gene_id=rownames(table),table,check.names=FALSE),
 file=file.path(argv[[3]],"reference-de.tsv"),sep="\t",row.names=FALSE,quote=FALSE)
