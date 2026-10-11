# Authorship and CRediT: two things only the authors can settle

Written 2026-10-11, after reordering the byline to match the portal form. **Neither item
is a defect I should fix by guessing** — both require a statement from the authors about
what actually happened.

---

## 1. The submission form asserts more than the manuscript does

PeerJ's form presents five questions and states, for each category:

> **"Every author must have at least one contribution from this category."**

Every author's box is ticked for **every** question. Compared against the CRediT
statement the manuscript actually prints, 15 answers disagree — all in the direction of
the form claiming more than the paper records:

| form question | who the form ticks | who the printed statement credits |
| --- | --- | --- |
| conceived and designed the experiments | all five | Alnahari, Alnahri |
| performed the experiments | all five | Alnahari |
| analyzed the data | all five | Alnahari |
| drafted the work | all five | Alnahari, Hasanin, Arbaaeen, Alsaig, Alnahri *(per the initials form)* / Alnahari only *(per the printed form)* |
| revised it critically | all five | all five ✅ |

Nothing disagrees in the "revised it critically" row; the disagreement is concentrated in
Category 1.

**Why this matters.** A published paper carries the CRediT statement, and a reader,
an editor or an integrity check comparing the two would see the form asserting
contributions the paper does not. The two must agree.

**The choice is the authors' alone:**

- If Arbaaeen, Alsaig and Hasanin really did contribute to conception, execution or
  analysis, the **manuscript statement must be widened** to say so — and the roles
  assigned must be true.
- If they did not, the **form's ticks are wrong** and should be un-ticked, unless PeerJ's
  "every author in every category" rule forces them.

I have not written either version, because inventing a CRediT role to make two documents
agree would be fabricating a claim of authorship rather than reconciling one.

---

## 2. The manuscript carries TWO CRediT statements and they differ

There are two statements in the source. `source/convert_to_peerj.py` **drops
`\authorcontributions`** and prints the full-name form from `source/paper_source.py`, so
only one reaches the PDF — but they disagree, which is a latent trap for whoever edits the
"wrong" one next.

| statement | where | printed? |
| --- | --- | --- |
| initials form (`W.A.`, `A.Ar.`, …) | `source/main.tex` `\authorcontributions` | **no** — dropped by the converter |
| full-name form | `source/paper_source.py` `CREDIT` | **yes** — this is what the PDF shows |

The disagreements:

| author | main.tex says | printed PDF says |
| --- | --- | --- |
| Alnahari | draft, not review-editing | draft **and** review-editing |
| Hasanin | validation **and draft** | validation and review-editing |
| Arbaaeen | funding **and draft** | funding and review-editing |
| Alsaig | review-editing **and draft** | review-editing |
| Alnahri | conceptualization, validation, **draft** | conceptualization, validation, review-editing |

The printed version is more plausible — "everyone drafted it" is unusual, and the
initials form's grouping is ambiguous. **Decide which is true, then make the other agree
or delete it**, so the manuscript states its contributions once.

---

## What I did change, and why that is safe

The byline order only. Ammar Arbaaeen is now first. **No CRediT role was reassigned** —
the sentences were reordered to match the byline and the roles are byte-for-byte what was
recorded. Author order and CRediT roles are independent; ICMJE states the order "is to be
decided collectively by the author group", so moving a name does not move a role.

Note that this is exactly the tension item 1 exposes: the byline now puts Arbaaeen first
while the statement credits him with funding and review only, and credits Alnahari with
the original draft and the software. That is permitted, but it is the kind of thing an
editor notices. Confirm it reflects the real division of labour.

---

## Also confirm

PeerJ asks that author order be agreed by all authors. The form had Arbaaeen first and the
manuscript had Alnahari first, so one of the two was stale. The byline now matches the
form. **Make sure the form was the correct one** and not a form-entry slip.
