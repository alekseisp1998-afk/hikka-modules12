# meta developer: OpenAI
# scope: hikka_only
# requires: hikka

from .. import loader, utils


@loader.tds
class CheckersOnlineMod(loader.Module):
    """Шашки 1×1 — сопернику Hikka не нужна."""
    strings = {"name": "CheckersOnline"}

    def __init__(self):
        self.games = {}
        self.next_id = 1

    def _new_board(self):
        board = [[None for _ in range(8)] for _ in range(8)]

        for r in range(3):
            for c in range(8):
                if (r + c) % 2:
                    board[r][c] = "b"

        for r in range(5, 8):
            for c in range(8):
                if (r + c) % 2:
                    board[r][c] = "w"

        return board

    def _inside(self, r, c):
        return 0 <= r < 8 and 0 <= c < 8

    def _moves(self, board, color):
        directions = [
            (-1, -1),
            (-1, 1),
            (1, -1),
            (1, 1),
        ]

        normal = []
        captures = []

        for r in range(8):
            for c in range(8):
                piece = board[r][c]

                if piece not in (color, color.upper()):
                    continue

                king = piece.isupper()

                for dr, dc in directions:
                    nr, nc = r + dr, c + dc

                    can_go = (
                        king
                        or (color == "w" and dr < 0)
                        or (color == "b" and dr > 0)
                    )

                    if (
                        can_go
                        and self._inside(nr, nc)
                        and board[nr][nc] is None
                    ):
                        normal.append((r, c, nr, nc, None))

                    jr, jc = r + 2 * dr, c + 2 * dc

                    if (
                        can_go
                        and self._inside(nr, nc)
                        and self._inside(jr, jc)
                        and board[nr][nc] is not None
                        and board[nr][nc].lower() != color
                        and board[jr][jc] is None
                    ):
                        captures.append(
                            (r, c, jr, jc, (nr, nc))
                        )

        return captures if captures else normal

    def _move(self, game, uid, r, c, nr, nc):
        color = "w" if uid == game["white"] else "b"

        valid = [
            move
            for move in self._moves(game["board"], color)
            if move[:4] == (r, c, nr, nc)
        ]

        if not valid:
            return False, "❌ Такой ход невозможен."

        _, _, _, _, taken = valid[0]

        piece = game["board"][r][c]
        game["board"][r][c] = None
        game["board"][nr][nc] = piece

        if taken:
            tr, tc = taken
            game["board"][tr][tc] = None

        if piece == "w" and nr == 0:
            game["board"][nr][nc] = "W"
        elif piece == "b" and nr == 7:
            game["board"][nr][nc] = "B"

        opponent = "b" if color == "w" else "w"

        has_piece = any(
            game["board"][rr][cc]
            and game["board"][rr][cc].lower() == opponent
            for rr in range(8)
            for cc in range(8)
        )

        if not has_piece or not self._moves(game["board"], opponent):
            game["winner"] = uid
            return True, f"🏆 Победил игрок <code>{uid}</code>!"

        game["turn"] = opponent
        return True, None

    def _cell_text(self, piece, dark):
        if piece == "w":
            return "⚪"
        if piece == "b":
            return "⚫"
        if piece in ("W", "B"):
            return "👑"

        return "▪️" if dark else "▫️"

    def _keyboard(self, game):
        rows = []
        selected = game.get("selected")

        for r in range(8):
            row = []

            for c in range(8):
                text = self._cell_text(
                    game["board"][r][c],
                    (r + c) % 2 == 1,
                )

                if selected == (r, c):
                    text = "🔵" + text

                row.append(
                    {
                        "text": text,
                        "callback": self._cell_callback,
                        "args": (game["id"], r, c),
                    }
                )

            rows.append(row)

        rows.append(
            [
                {
                    "text": "🏳️ Сдаться",
                    "callback": self._giveup_callback,
                    "args": (game["id"],),
                }
            ]
        )

        return rows

    def _text(self, game, extra=""):
        turn = (
            "⚪ Белые"
            if game["turn"] == "w"
            else "⚫ Чёрные"
        )

        turn_id = (
            game["white"]
            if game["turn"] == "w"
            else game["black"]
        )

        text = (
            "🎲 <b>ШАШКИ 1×1</b>\n\n"
            f"⚪ Белые: <code>{game['white']}</code>\n"
            f"⚫ Чёрные: <code>{game['black']}</code>\n\n"
            f"➡️ Ход: <b>{turn}</b>\n"
            f"👤 ID игрока: <code>{turn_id}</code>\n"
        )

        if game.get("selected") is not None:
            r, c = game["selected"]
            text += (
                f"\n🔵 Выбрана: "
                f"<b>{chr(65 + c)}{r + 1}</b>\n"
                "Нажми клетку назначения."
            )
        else:
            text += "\nНажми сначала на свою шашку."

        if extra:
            text += f"\n\n{extra}"

        return text

    async def _safe_edit(self, call, text, markup):
        if not call:
            return False

        try:
            await call.edit(
                text,
                reply_markup=markup,
                parse_mode="html",
            )
            return True
        except Exception:
            return False

    async def _update(self, game, extra=""):
        text = self._text(game, extra)
        markup = self._keyboard(game)

        for key in ("white_call", "black_call"):
            call = game.get(key)
            if call:
                await self._safe_edit(call, text, markup)

    async def _make_game_form(self, game, uid, message, extra):
        """Создаёт игровую форму и разрешает нажимать её обоим игрокам."""
        allowed = [
            game["white"],
            game["black"],
        ]

        return await self.inline.form(
            text=self._text(game, extra),
            message=message,
            reply_markup=self._keyboard(game),
            disable_security=True,
            always_allow=allowed,
        )

    async def _accept_callback(self, call, game_id, target_id):
        game = self.games.get(game_id)

        if not game or game.get("status") != "invite":
            await call.answer(
                "Приглашение уже недействительно.",
                show_alert=True,
            )
            return

        if call.from_user.id != target_id:
            await call.answer(
                "Это приглашение предназначено другому игроку.",
                show_alert=True,
            )
            return

        game["status"] = "playing"
        game["black_call"] = call
        game["selected"] = None

        # Сразу превращаем сообщение с приглашением в игровую доску.
        try:
            await call.edit(
                self._text(
                    game,
                    "🎮 Игра началась! Ты играешь чёрными.",
                ),
                reply_markup=self._keyboard(game),
                parse_mode="html",
            )
        except Exception:
            pass

        # Создаём отдельную игровую форму для белых.
        try:
            host_msg = await self.client.send_message(
                game["white"],
                "🎲 Игра началась!\n"
                "Открываю игровое поле…",
            )

            game["white_call"] = await self._make_game_form(
                game,
                game["white"],
                host_msg,
                "🎮 Игра началась! Ты играешь белыми.",
            )

        except Exception as e:
            game["white_call"] = None

            # Если форму белых создать не получилось,
            # возвращаем понятную информацию владельцу.
            try:
                await self.client.send_message(
                    game["white"],
                    "❌ Не удалось открыть игровое поле.\n"
                    f"Ошибка: <code>{type(e).__name__}</code>\n\n"
                    "Попробуй заново пригласить соперника.",
                )
            except Exception:
                pass

        await self._update(
            game,
            "🎮 Игра началась!",
        )

        try:
            await call.answer("🎮 Игра началась!")
        except Exception:
            pass

    async def _decline_callback(self, call, game_id, target_id):
        game = self.games.get(game_id)

        if not game or game.get("status") != "invite":
            await call.answer(
                "Приглашение уже недействительно.",
                show_alert=True,
            )
            return

        if call.from_user.id != target_id:
            await call.answer(
                "Это не твоё приглашение.",
                show_alert=True,
            )
            return

        game["status"] = "declined"

        try:
            await call.edit(
                "❌ <b>Игра отклонена.</b>",
                parse_mode="html",
            )
        except Exception:
            pass

        try:
            await self.client.send_message(
                game["white"],
                "❌ Соперник отклонил игру.",
            )
        except Exception:
            pass

        try:
            await call.answer("Приглашение отклонено.")
        except Exception:
            pass

    async def _cell_callback(self, call, game_id, r, c):
        game = self.games.get(game_id)

        if not game or game.get("status") != "playing":
            await call.answer(
                "Игра уже закончена.",
                show_alert=True,
            )
            return

        uid = call.from_user.id

        if uid not in (game["white"], game["black"]):
            await call.answer(
                "Ты не участник этой игры.",
                show_alert=True,
            )
            return

        color = (
            "w"
            if uid == game["white"]
            else "b"
        )

        if game["turn"] != color:
            await call.answer(
                "Сейчас ход соперника.",
                show_alert=True,
            )
            return

        piece = game["board"][r][c]
        selected = game.get("selected")

        # Выбор своей шашки.
        if selected is None:
            if piece and piece.lower() == color:
                game["selected"] = (r, c)
                await self._update(game)

                try:
                    await call.answer("Шашка выбрана.")
                except Exception:
                    pass
            else:
                await call.answer(
                    "Выбери свою шашку.",
                )
            return

        # Нажали на выбранную клетку ещё раз.
        if selected == (r, c):
            game["selected"] = None
            await self._update(game)

            try:
                await call.answer("Выбор отменён.")
            except Exception:
                pass
            return

        sr, sc = selected

        ok, result = self._move(
            game,
            uid,
            sr,
            sc,
            r,
            c,
        )

        if not ok:
            await call.answer(
                result,
                show_alert=True,
            )
            return

        game["selected"] = None

        if result:
            game["status"] = "finished"

            await self._update(
                game,
                result,
            )

            try:
                await call.answer("🏆 Победа!")
            except Exception:
                pass

            return

        await self._update(
            game,
            "✅ Ход принят.",
        )

        try:
            await call.answer("Ход принят.")
        except Exception:
            pass

    async def _giveup_callback(self, call, game_id):
        game = self.games.get(game_id)

        if not game or game.get("status") != "playing":
            await call.answer(
                "Игра уже закончена.",
                show_alert=True,
            )
            return

        uid = call.from_user.id

        if uid not in (game["white"], game["black"]):
            await call.answer(
                "Ты не участник игры.",
                show_alert=True,
            )
            return

        winner = (
            game["black"]
            if uid == game["white"]
            else game["white"]
        )

        game["status"] = "finished"

        await self._update(
            game,
            "🏳️ <b>Игра окончена.</b>\n"
            f"🏆 Победитель: <code>{winner}</code>\n"
            f"🏳️ Сдался: <code>{uid}</code>",
        )

        try:
            await call.answer("Ты сдался.")
        except Exception:
            pass

    @loader.command()
    async def шашки(self, message):
        """Пригласить пользователя: .шашки @username или ответом."""
        me = await message.client.get_me()
        reply = await message.get_reply_message()
        args = utils.get_args_raw(message).strip()

        target = None

        if reply:
            try:
                target = await message.client.get_entity(
                    reply.sender_id
                )
            except Exception:
                pass

        elif args:
            try:
                target = await message.client.get_entity(
                    args.split()[0]
                )
            except Exception:
                pass

        if not target:
            await utils.answer(
                message,
                "❌ Использование:\n"
                "<code>.шашки @username</code>\n"
                "или ответь на сообщение пользователя "
                "командой <code>.шашки</code>.",
            )
            return

        if target.id == me.id:
            await utils.answer(
                message,
                "❌ Нельзя играть самому с собой.",
            )
            return

        if getattr(target, "bot", False):
            await utils.answer(
                message,
                "❌ Ботов приглашать нельзя.",
            )
            return

        for game in self.games.values():
            if game.get("status") in (
                "invite",
                "playing",
            ):
                if (
                    me.id in (
                        game["white"],
                        game["black"],
                    )
                    or target.id in (
                        game["white"],
                        game["black"],
                    )
                ):
                    await utils.answer(
                        message,
                        "❌ Один из игроков уже занят.",
                    )
                    return

        game_id = str(self.next_id)
        self.next_id += 1

        game = {
            "id": game_id,
            "status": "invite",
            "board": self._new_board(),
            "white": me.id,
            "black": target.id,
            "turn": "w",
            "selected": None,
            "white_call": None,
            "black_call": None,
            "invite_call": None,
        }

        self.games[game_id] = game

        try:
            invite_msg = await message.client.send_message(
                target.id,
                "🎲 Тебя приглашают сыграть в шашки!",
            )

            game["invite_call"] = await self.inline.form(
                text=(
                    "🎲 <b>ШАШКИ 1×1</b>\n\n"
                    f"👤 Игрок <code>{me.id}</code> "
                    "приглашает тебя сыграть.\n\n"
                    "📱 Hikka устанавливать НЕ нужно.\n\n"
                    "Нажми кнопку ниже."
                ),
                message=invite_msg,
                reply_markup=[
                    [
                        {
                            "text": "🎮 Принять игру",
                            "callback": self._accept_callback,
                            "args": (
                                game_id,
                                target.id,
                            ),
                        },
                        {
                            "text": "❌ Отклонить",
                            "callback": self._decline_callback,
                            "args": (
                                game_id,
                                target.id,
                            ),
                        },
                    ]
                ],
                disable_security=True,
                always_allow=[target.id],
            )

            await utils.answer(
                message,
                "🎲 <b>Приглашение отправлено!</b>\n\n"
                f"👤 Соперник: "
                f"<b>{getattr(target, 'first_name', 'игрок')}</b>\n\n"
                "Сопернику Hikka не нужна — "
                "он просто нажимает "
                "«🎮 Принять игру».",
            )

        except Exception as e:
            self.games.pop(game_id, None)

            await utils.answer(
                message,
                "❌ <b>Не удалось отправить приглашение.</b>\n\n"
                f"Ошибка: <code>{type(e).__name__}</code>",
            )

    @loader.command()
    async def отменитьшашки(self, message):
        """Отменить своё приглашение."""
        me = await message.client.get_me()
        found = False

        for game_id, game in list(self.games.items()):
            if (
                game.get("status") == "invite"
                and game.get("white") == me.id
            ):
                found = True
                self.games.pop(game_id, None)

                try:
                    if game.get("invite_call"):
                        await game["invite_call"].edit(
                            "❌ <b>Приглашение отменено.</b>",
                            parse_mode="html",
                        )
                except Exception:
                    pass

        await utils.answer(
            message,
            (
                "✅ Приглашение отменено."
                if found
                else "❌ Активного приглашения нет."
            ),
        )
