# Fixed candidate method. Inputs are public counts and participant-declared design.
# Run only in the allocated analysis environment; no installation or network.
args <- commandArgs(trailingOnly=TRUE)
if (length(args)!=4L) stop("EXPECTED_COUNTS_DESIGN_OUTPUT_VERSION")
if (as.character(utils::packageVersion("edgeR"))!=args[4]) stop("EDGER_VERSION")
suppressPackageStartupMessages(library(edgeR))
d <- read.delim(args[2], stringsAsFactors=FALSE, check.names=FALSE)
if (!identical(names(d),c("library_id","donor_id","condition"))) stop("DESIGN_COLUMNS")
if (anyDuplicated(d$library_id) || any(!d$condition %in% c("control","stim"))) stop("DESIGN")
tab <- table(d$donor_id,d$condition)
if (nrow(tab)<2 || ncol(tab)!=2 || any(tab!=1)) stop("PAIRED_DONOR_DESIGN")
x <- read.delim(args[1],row.names=1,check.names=FALSE)
if (!setequal(colnames(x),d$library_id)) stop("COUNT_LIBRARIES")
x <- as.matrix(x[,d$library_id,drop=FALSE])
if (any(!is.finite(x)) || any(x<0) || any(x!=floor(x))) stop("INTEGER_COUNTS")
d$donor_id <- factor(d$donor_id)
d$condition <- factor(d$condition,levels=c("control","stim"))
design <- model.matrix(~donor_id+condition,data=d)
if (qr(design)$rank!=ncol(design)) stop("DESIGN_RANK")
y <- DGEList(counts=x)
keep <- filterByExpr(y,design=design,min.count=10,min.total.count=15,large.n=10,min.prop=0.7)
if (sum(keep)<2) stop("INSUFFICIENT_EXPRESSED_GENES")
y <- y[keep,,keep.lib.sizes=FALSE]
y <- calcNormFactors(y,method="TMM")
y <- estimateDisp(y,design,robust=FALSE)
fit <- glmQLFit(y,design,robust=FALSE,legacy=TRUE)
test <- glmQLFTest(fit,coef="conditionstim")
t <- topTags(test,n=Inf,sort.by="none")$table
result <- data.frame(gene_id=rownames(t),t,check.names=FALSE)
write.table(result,file=file.path(args[3],"de.tsv"),sep="\t",row.names=FALSE,quote=FALSE)
execution <- data.frame(key=c("method_id","R","edgeR","limma","formula","unit","donors","tested_genes","contrast"),
 value=c("bw01-paired-edger-ql/0.1",as.character(getRversion()),as.character(packageVersion("edgeR")),
 as.character(packageVersion("limma")),"~ donor_id + condition","donor",
 nlevels(d$donor_id),nrow(result),"stim-control"))
write.table(execution,file=file.path(args[3],"execution.tsv"),sep="\t",row.names=FALSE,quote=FALSE)
