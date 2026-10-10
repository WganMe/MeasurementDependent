# PeerJ submission-portal values

These are the values PeerJ's submission portal asks for that are **not** carried in the
manuscript. `wlpeerj.cls` disables the keywords block, so Subjects and Keywords are
entered in the portal only. Every value below is copied from the manuscript source
(`source/main.tex`), not retyped.

## Title

> Measurement-Dependent Clustering in the Growing Urban Observatory Sensor Network

(9 words. PeerJ does not judge novelty, so a descriptive title is fine; see the README for
the optional retitle.)

## Abstract

199 words, the same text as the manuscript abstract. PeerJ does not impose a strict word
cap, but paste the manuscript abstract verbatim so the portal copy cannot drift. The count is
taken by `source/paper_source.py:abstract_word_count` and checked against the cover page and
the bundle at build time, so the three cannot state different lengths again.

## Subjects (choose from PeerJ's own list at the portal)

PeerJ's subjects are a fixed taxonomy; the portal presents them and you tick the ones
that apply. These are copied from PeerJ's list exactly as it spells them (verified at
peerj.com/subjects/ and in the subject URL), so they can be matched at the portal:

- **Spatial and Geographic Information Systems** (primary — PeerJ names this subject
  "Systems", not "Science"; the published example paper's own subject line reads
  "Spatial and Geographic Information Science", so take whichever the portal offers)
- **Environmental Monitoring & Management**
- **Data Mining and Machine Learning**
- **Internet of Things**
- **Network Science and Online Social Networks**

Each is a live PeerJ subject overlay, so this is PeerJ's naming rather than a paraphrase:

```text
https://peerj.com/subjects/spatial-and-geographic-information-systems/
https://peerj.com/subjects/environmental-monitoring-management/
https://peerj.com/subjects/data-mining-and-machine-learning/
https://peerj.com/subjects/internet-of-things/
https://peerj.com/subjects/network-science-and-online-social-networks/
```

## Keywords (free text, if the portal asks)

From `\keyword{}` in `main.tex`:

> urban sensor networks; smart-city infrastructure; spatial clustering; spatial
> asymmetry; point-pattern analysis; longitudinal analysis

## Authors and affiliations

| # | Author | Affiliation | ORCID |
| --- | --- | --- | --- |
| 1 | Wael Alnahari (corresponding) | Department of Information Systems, Faculty of Computing and Information Technology, King Abdulaziz University, Jeddah 21589, Saudi Arabia | 0000-0001-5247-3713 |
| 2 | Ammar Arbaaeen | Department of Computer Science, College of Computer and Information Systems, Umm Al-Qura University, Mecca 24381, Saudi Arabia | 0000-0003-2165-3185 |
| 2 | Ammar Alsaig | as above (Umm Al-Qura University) | 0000-0002-6756-9766 |
| 1 | Tawfiq Hasanin | as author 1 (King Abdulaziz University) | 0000-0003-1072-278X |
| 3 | Wasem Alnahri | Independent Researcher, Mecca 24331, Saudi Arabia | 0009-0004-6963-5773 |

Corresponding e-mail: `walnahari0004@stu.kau.edu.sa`.

## Data and code availability

The Data Availability statement in the manuscript points at
`https://doi.org/10.5281/zenodo.23099939`. PeerJ's open-data policy requires materials,
code and raw data at submission; the deposit is the DOI to supply at the portal.

## Impact toolkit — no action at submission

The "Impact toolkit" page shown at the portal is a **post-publication** promotion hub
(sharing, X/Twitter, blogging). It states plainly: *"As you have not published any articles
at PeerJ, there isn't much to do here yet."* Nothing on it is a submission requirement, and
nothing in it changes the manuscript. When the article is published, the toolkit's tasks
(X post, email the article, add it to a relevant Wikipedia article) become available.
