# Player profile spot checks (2026-10-22)

These checks corroborate selected fields, not all 133 players. Provider IDs come
from the existing source archive; official sites do not certify API-Football IDs.
No field below is used to backdate availability or infer transfer intervals.

| Source player ID | Player | Official page | Corroborated fields |
| --- | --- | --- | --- |
| 502 | Joshua Kimmich | https://fcbayern.com/en/teams/first-team/joshua-kimmich | Birth 1995-02-08; Rottweil; height 1.77 m; weight 75 kg; German nationality |
| 622 | Aymeric Laporte | https://www.athletic-club.eus/en/players/aymeric-laporte/ | Birth 1994-05-27; Agen, France; height 1.91 m |

API-Football documents its profile and career endpoints here:
https://www.api-football.com/news/post/api-football-new-release-available

Laporte discrepancy: the captured API profile reports height 189 cm, while the
official Athletic profile reports 1.91 m. A `profile_field_conflict` review records
both values and the official URL. Neither value silently overwrites the other.
His Spanish nationality and French birthplace are distinct fields, not a conflict.

Operational exports and hashed API responses are local ignored data, not embedded
in this document. The live export identifies missing fields explicitly. A profile
response is source-reported information; `profile_observed` is not an assertion of
complete career history or independent verification of every field.
