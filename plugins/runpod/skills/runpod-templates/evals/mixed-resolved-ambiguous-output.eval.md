# Apply verified metadata and still output when another model is ambiguous

## Prompt

This UI workflow references two missing models. One has an exact publisher file and hash;
the other has two credible exact-filename candidates with no evidence distinguishing them.
Repair it as far as you safely can.

## Expected behavior

The agent adds metadata only for the verified model and omits the ambiguous model from the
temporary manifest. It does not pause when it discovers the ambiguity. It first runs the
finalizer with `--allow-unresolved`, producing one partial repaired JSON whose verified
record is attached and whose ambiguous loader selection is unchanged.

The same final handoff starts with the one full absolute `Fixed workflow` path, says that
one model still needs attention, briefly names the model whose download information was
added, and then presents the two possible files with one consolidated choice question. It
does not provide inventory, manifest, normalized JSON files, hashes, or long URLs.

## Assertions

- Creates and reports the partial workflow before asking the ambiguity question.
- Applies the verified record and does not apply either ambiguous candidate.
- Names the verified model without showing a technical table by default.
- (handoff-contract assertions owned by always-output-workflow.eval.md)
