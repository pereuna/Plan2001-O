Tarkistin tilanteen:

- `main` on puhdas ja synkassa: `87edb4d` = `origin/main` (myös remote vahvistaa saman SHA:n).
- Ainoa keskeneräinen muutos on worktreessä `build/e4-isolated` (detached HEAD `10d9fcd`), tiedostossa `sys/src/9/port/devcons.c`.
- Se muutos on sisällöltään **identtinen** jo committoidun ja pushatun `f60211d` (E4 Qppid) kanssa, eli kyse on vanhentuneesta kokeiluworktreestä — ei mitään committoitavaa tai pushattavaa.

Eli commit ja push ovat jo valmiit; mitään ei tarvitse tehdä. Haluatko, että siivoan vanhentuneen `build/e4-isolated`-worktreen (reset/poisto)?
