# Independent raw-count aggregation check. Uses Matrix rather than the Python stream reducer.
args <- commandArgs(trailingOnly=TRUE)
stopifnot(length(args)==4L)
rawdir <- args[1];public <- args[2];truth <- jsonlite::fromJSON(args[3]);output <- args[4]
metadata <- read.delim(gzfile(file.path(rawdir,"GSE96583_batch2.total.tsne.df.tsv.gz")),
                      row.names=1,check.names=FALSE,stringsAsFactors=FALSE)
genes <- read.delim(gzfile(file.path(rawdir,"GSE96583_batch2.genes.tsv.gz")),
                   header=FALSE,stringsAsFactors=FALSE)
dataset <- jsonlite::fromJSON(file.path(public,"dataset.json"))
observed <- as.matrix(read.delim(file.path(public,"counts.tsv"),row.names=1,check.names=FALSE))
stopifnot(identical(rownames(observed),genes[[1]]),!anyDuplicated(rownames(observed)))
annotation <- read.delim(file.path(public,"gene-annotations.tsv"),check.names=FALSE,stringsAsFactors=FALSE)
stopifnot(identical(annotation$gene_id,genes[[1]]),identical(annotation$symbol,genes[[2]]))
map <- truth$sample_map
reference <- matrix(0,nrow=nrow(genes),ncol=nrow(map),dimnames=list(genes[[1]],map$library_id))
for (condition in c("ctrl","stim")) {
    accession <- if(condition=="ctrl") "GSM2560248" else "GSM2560249"
    mtx <- if(condition=="ctrl") "GSM2560248_2.1.mtx.gz" else "GSM2560249_2.2.mtx.gz"
    meta <- metadata[metadata$stim==condition,,drop=FALSE]
    barcode <- readLines(gzfile(file.path(rawdir,paste0(accession,"_barcodes.tsv.gz"))))
    stopifnot(identical(sub("-.*$","",barcode),sub("-.*$","",rownames(meta))))
    counts <- Matrix::readMM(gzfile(file.path(rawdir,mtx)))
    stopifnot(nrow(counts)==nrow(genes),ncol(counts)==nrow(meta))
    for (j in which(map$source_condition==condition)) {
        use <- !is.na(meta$ind) & !is.na(meta$cell) & !is.na(meta$multiplets) &
           as.character(meta$ind)==as.character(map$source_donor[j]) &
               meta$cell==dataset$cell_type & meta$multiplets=="singlet"
        if (!isTRUE(sum(use)>=dataset$min_cells_per_donor_condition)) {
        print(list(condition=condition,donor=map$source_donor[j],selected=sum(use),
                   donor_matches=sum(as.character(meta$ind)==as.character(map$source_donor[j])),
                   cell_type=dataset$cell_type,cell_types=table(meta$cell),multiplets=table(meta$multiplets),
                   columns=names(meta),first_rows=head(meta,2)))
        stop("INDEPENDENT_AGGREGATION_SELECTION_MISMATCH")
    }
        reference[,j] <- Matrix::rowSums(counts[,which(use),drop=FALSE])
    }
    rm(counts);gc()
}
observed <- observed[,colnames(reference),drop=FALSE]
stopifnot(identical(dim(observed),dim(reference)),all(observed==reference))
write.table(data.frame(check="all_raw_aggregate_entries_equal",passed=TRUE,
                       genes=nrow(reference),libraries=ncol(reference)),
            file=output,sep="\t",row.names=FALSE,quote=FALSE)
