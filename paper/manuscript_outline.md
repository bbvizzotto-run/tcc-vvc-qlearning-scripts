# Manuscript outline

## Working title

**QoE-Aware Adaptive Streaming under Content-Dependent VVC Segment Variability:
Model-Based Control versus Tabular Reinforcement Learning**

## Central claim

Under the frozen multi-content benchmark with measured VVC payloads, RobustMPC
achieved higher objective QoE than tabular Q-Learning. The lower startup delay
of Q-Learning did not compensate for its higher rebuffering, frequent
representation changes, and lower delivered quality.

The contribution is the VVC-specific measured benchmark, evaluation protocol,
and empirical evidence. RobustMPC must be described as an adapted established
baseline, not as a newly proposed algorithm.

## Article structure

1. **Introduction**
   - Motivate the gap between nominal bitrate ladders and measured VVC segment
     payloads.
   - State the research question and contributions.
2. **Related work**
   - VVC streaming and segment variability.
   - Model-based ABR, including RobustMPC.
   - Reinforcement-learning ABR and negative-result reporting.
3. **Measured multi-content VVC dataset**
   - Sources, normalization, encoding, independent access points, PSNR-Y and
     provenance.
   - Use Figure 1, Figure 2, Table 1 and Table 2.
4. **ABR controllers and experimental protocol**
   - Static, throughput, BOLA-BASIC, RobustMPC and tabular Q-Learning.
   - Frozen parameters, traces, seeds, decision-information policy and paired
     statistical analysis.
5. **Results**
   - Lead with the pre-specified primary contrast (Figure 4 and Table 4).
   - Then report the overall metric profile (Figure 3 and Table 3).
   - Discuss content/trace heterogeneity (Figure 6), including the single
     Elephants Dream low-start exception.
6. **Discussion**
   - Interpret the startup--rebuffering trade-off (Figure 5).
   - Relate switching instability to partial state coverage (Figure S1).
   - Do not claim causality for state coverage.
7. **Limitations and threats to validity**
   - Fixed contents and traces, deterministic baselines, per-content training,
     network abstraction and PSNR-Y limitations.
8. **Conclusion**
   - State that robust model-based planning is the strongest controller under
     the evaluated VVC conditions, not universally.

## Claims to avoid

- RobustMPC is a novel contribution of this work.
- The confidence intervals represent random sampling of all videos or networks.
- Partial tabular-state coverage caused the Q-Learning result.
- The observed superiority generalizes to every VVC service or network.
