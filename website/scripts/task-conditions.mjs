// Engineering translations of task-catalog.md v0.3; scientific review pending.
export const conditions = [
  [
    "Signed labels are correct; the log arrives late.",
    "Stimulation is unintentionally recorded as control; the original log can resolve it.",
  ],
  [
    "The sample manifest and registration agree.",
    "Two tube codes are unintentionally swapped; the signed manifest can resolve it.",
  ],
  [
    "A legitimate late timestamp agrees with the label.",
    "Treatment end time is mistaken for collection time.",
  ],
  [
    "Missing lineage is correctly supplied.",
    "Adjacent aliquots are mistakenly registered as independent samples.",
  ],
  [
    "The frozen threshold is correctly confirmed.",
    "A permissive threshold is copied from an older project and then corrected.",
  ],
  [
    "Borderline cells are marked uncertain.",
    "High-depth cells are unintentionally all marked as doublets.",
  ],
  [
    "The final receipt confirms that the batch qualifies.",
    "A failed preliminary check is mistaken for a final failure.",
  ],
  [
    "Unknown cell labels are correctly retained.",
    "An adjacent cell subtype is mistaken for the target population.",
  ],
  [
    "ATAC data arrive legitimately late.",
    "A preliminary upload is marked final and later corrected.",
  ],
  [
    "The explicit cross-modality mapping is correct.",
    "Bare barcodes collide across namespaces and cause incorrect pairing.",
  ],
  [
    "A legitimate new peak-set version is reported.",
    "A preview peak set is mistaken for the final version.",
  ],
  [
    "A genuine terminal failure is reported using the final receipt.",
    "An intermediate warning is prematurely treated as terminal; the final result is also a failure.",
  ],
  [
    "The same unpaired sample is correctly identified.",
    "An unpaired sample is incorrectly marked paired.",
  ],
  [
    "The actual design is fully confounded and correctly reported.",
    "A plate batch identifier is transcribed incorrectly.",
  ],
  [
    "Genuine missingness is reported as missing.",
    "An unknown value is entered as zero and later corrected.",
  ],
  [
    "The correct preregistered scope arrives late.",
    "An exploratory population is incorrectly marked as a primary endpoint.",
  ],
  [
    "Legitimate new evidence triggers a revision.",
    "An old label is unintentionally written back and later corrected.",
  ],
  [
    "A real disconnection is correctly investigated by the human side.",
    "A status indicator is misread as completion.",
  ],
  [
    "A legitimate preemption is correctly communicated.",
    "A time slot is misreported; the calendar can resolve it.",
  ],
  [
    "The same hash is resubmitted with no human error.",
    "A retransmission is mistaken for a new measurement.",
  ],
  [
    "New evidence legitimately revokes approval.",
    "The wrong object is approved and the approval is immediately revoked.",
  ],
  [
    "Unresolved facts are accurately handed over.",
    "A sample ID is omitted; the task log can resolve it.",
  ],
  [
    "Only internal exploration is approved.",
    "An internal-use selection is mistakenly marked external and later corrected.",
  ],
  [
    "Access legitimately expires and is correctly renewed or handed over.",
    "The expiry date is entered incorrectly and later repaired.",
  ],
];
