# Proposed figure captions

1. **Experimental workflow.** Source preparation, VVC encoding and decoding,
   measured segment manifests, ABR evaluation, and content-balanced statistical
   analysis used in the frozen protocol.
2. **Content-dependent VVC segment variability.** Each point represents one
   independently encoded one-second segment. The black line connects the mean
   payload bitrate and mean PSNR-Y of the four representations. The bitrate axis
   is logarithmic to retain low-rate and high-complexity segments in the same
   view. Triangles at the upper boundary identify exact reconstructions assigned
   the 100 dB lossless cap; representation means use the uncapped recorded value.
3. **Overall controller results.** Metrics are first averaged across evaluation
   traces and contents within each training seed. Error bars denote 95% Student
   t intervals across the ten Q-Learning seeds. Deterministic baselines repeat
   identically across seeds.
4. **Pre-specified primary contrast.** Mean difference in objective reward
   between Q-Learning and RobustMPC, overall and separately by content. Negative
   values favor RobustMPC; bars denote 95% Student t intervals across training
   seeds.
5. **Startup--rebuffering trade-off.** Overall mean startup delay and
   rebuffering rate for the five controllers. The lower-left region is preferred.
6. **Content and network-condition heterogeneity.** Mean objective-reward
   difference Q-Learning − RobustMPC for each content--trace combination.
   Negative values favor RobustMPC. The Elephants Dream low-start trace is the
   only localized positive contrast.
7. **Supplementary Figure S1 — state-space coverage.** Percentage of the 168
   tabular states visited during Q-Learning training for each content and seed.
   This diagnostic supports discussion but does not establish a causal mechanism.
