## Summary
<!-- What does this PR do? One paragraph. -->

## Type of change
- [ ] Bug fix
- [ ] New rule (requires genetic counselor sign-off)
- [ ] Whitelist variant addition (requires evidence documentation)
- [ ] Surveillance system change
- [ ] Infrastructure / tooling
- [ ] Documentation

## Clinical review (required for rule/whitelist changes)
<!-- Skip this section for infrastructure PRs -->

**Genetic counselor:**
<!-- Name and credentials of the reviewer -->

**Evidence sources (PMIDs):**
<!-- List the publications reviewed -->

**Ancestry limitations noted:**
<!-- Which populations was the evidence from? -->

**Approved user-facing text:**
<!-- Paste the exact recommendation text that was reviewed and approved -->

## Testing
- [ ] `make test` passes locally
- [ ] `make lint` passes
- [ ] New tests added for new logic
- [ ] Tested against synthetic data (`make run-synthetic`)

## Data safety
- [ ] No real VCF files or genetic data committed
- [ ] No API keys or secrets committed
- [ ] `.gitignore` changes reviewed if applicable

## Checklist
- [ ] CHANGELOG updated
- [ ] No diagnostic language in recommendation text ("you have", "you are diagnosed")
- [ ] Output tier is correct (tier_1/2/3)
- [ ] Disclaimer text present and accurate
- [ ] Rule ID is sequential and unique
