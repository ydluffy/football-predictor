# 生日冲突复核

复核日期：2026-10-22。只补充核验依据，不覆盖任何供应商原始字段，不批准跨源身份绑定。

## 官方资料支持本地生日的两项

| 球员 | API-Football ID | 本地生日 | football-data.org ID | 来源生日 |
| --- | --- | --- | --- | --- |
| Junior Firpo | 1564 | 1996-08-22 | 33037 | 1996-05-10 |
| Víctor García | 46790 | 1997-09-16 | 83333 | 1997-01-01 |

官方证据：

- Real Betis 球员页：https://www.realbetisbalompie.es/primer-equipo/jugador/junior-250738 ，姓名 Héctor Junior Firpo Adamés，生日 22-08-1996。
- Levante 球员页：https://www.levanteud.com/en/players/victor-garcia ，生日 Sep 16, 1997。

结论：本地生日获得独立官方支持。新增来源生日应继续作为冲突保留，不应拿它覆盖本地值。网页为本轮检索证据，尚未保存网页原始快照。

## 缩写或同名造成的候选碰撞

- F. Mendy 同时召回 Ferland Mendy 与 Formose Mendy；前者生日、球队相符，后者均不相符。
- L. Martinez 同时召回 Lisandro、Lautaro、Leandro、Loureins、Luis Martínez；仅 Lisandro 的生日和球队相符。
- 本地 Yuri 的完整姓名是 Yuri Berchiche Izeta（1990-02-10，Spain），来源 ID 13355 的 Yuri 为 1994-04-20、Brazil，球队也不同，不应合并。

以上碰撞根据现有源快照判别，不等于对所有候选身份进行了独立官网确认。现阶段继续保留候选与冲突，不静默删除候选以提高通过率。

## 比对修复

除实体简称外，使用已取得的 profile.name 以及 firstname + lastname 召回候选；不截断姓氏、不做模糊拼写匹配。生日及球队条件不放宽，多个候选仍需复核。完整姓名缺失时不会虚构姓名。
