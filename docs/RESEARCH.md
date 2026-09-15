# Learning methods and evidence

Vocab uses spaced retrieval practice. It does not measure brain capacity,
diagnose fatigue, certify CEFR proficiency, or guarantee a retention percentage.

## What the research supports

| Source | Finding used here | Implementation |
| --- | --- | --- |
| Cepeda et al. (2006), *Distributed practice in verbal recall tasks: A review and quantitative synthesis*, Psychological Bulletin 132, 354–380. [Paper](https://www.escholarship.org/content/qt3rr6q10c/qt3rr6q10c.pdf), [DOI](https://doi.org/10.1037/0033-2909.132.3.354) | Distributed practice generally benefits delayed recall. Effective spacing depends on the intended retention interval. | Schedule future reviews; distinguish early practice from due reviews. The paper does not specify this app's minute steps, queue positions or interval multipliers. |
| Karpicke & Roediger (2008), *The Critical Importance of Retrieval for Learning*, Science 319, 966–968. [Paper](https://learninglab.psych.purdue.edu/downloads/2008/2008_Karpicke_Roediger_Science.pdf), [DOI](https://doi.org/10.1126/science.1152408) | Repeated retrieval of foreign-language vocabulary improved delayed recall in the studied conditions. | Recall before revealing an answer; keep successful words in future reviews. Correct answers do not trigger automatic retirement. |
| Woźniak & Gorzelańczyk (1994), *Optimization of repetition spacing in the practice of learning*, Acta Neurobiologiae Experimentalis 54, 59–62. [Paper and abstract](https://ane.pl/index.php/ane/article/view/1003) | Investigates growing repetition intervals in paired-associate learning. | Background for adaptive spacing; this paper is not the specification of the implemented SM-2 equations. |
| Woźniak (1990), *Optimization of learning*, section 3.2. [Author's SM-2 specification](https://www.super-memory.org/archive/english/ol/sm2.htm) | Defines an auditable item-level interval and ease-factor algorithm. | Exact long-term recurrence in `vocab/scheduler.py`, with the explicit application policies below. SM-2's parameters are heuristic, not individually fitted coefficients. |
| Wilson (1927), *Probable Inference, the Law of Succession, and Statistical Inference*, JASA 22, 209–212. [DOI](https://doi.org/10.1080/01621459.1927.10502953) | Score interval for a binomial proportion. | `vocab/measurement.py` reports a 95% Wilson interval for practice-test accuracy. Independence is an approximation; the interval does not correct biased item selection, guessing or repeated exposure. |

## Scheduler specification

The four buttons map to SM-2 response quality: Again → 0, Hard → 3,
Good → 4, Easy → 5. Hard means correct recall with difficulty.

For successful long-term reviews:

```text
I(1) = 1 day
I(2) = 6 days
I(n) = ceil(I(n - 1) × EF), n > 2
EF' = max(1.3, EF + 0.1 - (5 - q) × (0.08 + (5 - q) × 0.02))
```

The initial ease factor is 2.5. Compute the interval using the previous ease,
then update ease. Failure resets the repetition count. There is no random
interval jitter, so previews and saved schedules use the same calculation.

### Application policies, not conclusions from the papers

- New cards use short learning steps: Again schedules 1 minute; Hard repeats
  at 10 minutes; the first Good schedules 10 minutes; the next Good graduates
  to 1 day. Easy graduates directly to 1 day. Relearning uses the same steps.
- A flashcard introduction is logged separately from recall. It starts the
  learning queue but does not contribute to reported recall accuracy.
- Missed and Hard cards return later in the session. Queue spacing is measured
  in intervening cards; it is not a guarantee that the scheduled minutes elapsed.
- Successful early practice of a review card preserves its due date, ease and
  repetition count. Failure still starts relearning. This prevents repeated
  same-session answers from inflating long-term intervals.
- Correct typing answers receive Good regardless of speed. Near-miss spelling
  uses the existing edit-distance heuristic. Multiple-choice quizzes provide
  feedback and logs but do not modify free-recall schedules.
- Intervals are capped at 36,500 days as an implementation limit.
- Timing is descriptive only. The default 30-second reporting filter is a
  configurable display policy, not evidence of distraction. New raw timings
  are preserved; explicit cleanup remains available for legacy maintenance.
- Session workload points, automatic batch sizing, queue mixing, interval
  bands (21 days), and suggested batch times remain convenience heuristics.
  They have not been validated as cognitive capacity or optimal study timing.

## Measurement and limits

Seven-day recall is `(Hard + Good + Easy) / rated recall attempts`, excluding
quiz and introduction logs. It is an observed practice score, not a predicted
probability of remembering later. Older flashcard introduction logs cannot
always be distinguished from genuine recall and may affect historical scores.

Time-of-day summaries describe activity and samples without diagnosing focus
or fatigue. Response times include reading and input time and differ by task.
Informal vocabulary tests report item scores and uncertainty. Their curated
level labels do not support an estimate of overall CEFR level or word count.

Legacy `stability`, `difficulty` and `retrievability` fields remain for database
compatibility. New stability mirrors the scheduled interval; difficulty is a
workload proxy derived from ease. The legacy exponential curve is illustrative,
not a fitted FSRS model, and is not used to set review intervals or rank the queue.

## Existing data

Launching Vocab does not replay history or clean timing data automatically.
Existing due dates remain until you review a card. Already retired cards stay
retired; use the word editor to reactivate them if desired. New reviews use
SM-2 from the stored interval, repetition count and ease factor.

Explicit history synchronization recalculates from a fixed new-card baseline
using the same scheduler as live reviews. It is deterministic and can change
legacy due dates. It excludes recognition logs and respects retirement. Legacy
naive timestamps are interpreted in the computer's local timezone; moving an
old database between timezones can change that interpretation.

The regression suite checks reference SM-2 sequences, failed and early reviews,
preview purity, replay consistency, timing neutrality, retirement, raw logging,
assessment uncertainty and terminal layout. Passing software tests verifies
implementation behavior; it is not a trial of learning effectiveness.
