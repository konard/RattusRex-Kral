import { Component, FormEvent, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { Link, Navigate, Route, BrowserRouter as Router, Routes, useNavigate, useParams } from "react-router-dom";
import { CalendarDays, Check, Dice5, LogOut, MessageSquare, Pencil, Plus, RefreshCw, Save, ScrollText, Search, Send, Shield, ShoppingBag, Swords, Trash2, Trophy, UserRound, UsersRound, X } from "lucide-react";
import { AbilityRoll, AdminUser, api, AttackRoll, CalendarSummary, Character, CharacterAttack, ChatMessage, DamageRoll, Inventory, InventoryItem, LeaderboardEntry, MagicItem, ROLE_LABELS, SavingThrowRoll, ShopResult, ShopTransactionLog, TOKEN_KEY, TransferLog, TransferTarget, User, UserRole } from "./api";
import "./styles.css";

const rarities = ["Обычный", "Необычный", "Редкий"];
// The game world started counting in-world time on this date; characters
// cannot be created (or spend downtime) earlier than it.
const GAME_EPOCH = "2025-06-01";
const hirelings = [
  { level: "Плохой", bonus: 0, cost: 1 },
  { level: "Хороший", bonus: 4, cost: 5 },
  { level: "Компетентный", bonus: 6, cost: 10 },
  { level: "Эксперт", bonus: 8, cost: 25 }
];
const characterClasses = [
  { name: "Бард", hitDie: "d8" },
  { name: "Варвар", hitDie: "d12" },
  { name: "Воин", hitDie: "d10" },
  { name: "Волшебник", hitDie: "d6" },
  { name: "Друид", hitDie: "d8" },
  { name: "Жрец", hitDie: "d8" },
  { name: "Изобретатель", hitDie: "d8" },
  { name: "Колдун", hitDie: "d8" },
  { name: "Монах", hitDie: "d8" },
  { name: "Паладин", hitDie: "d10" },
  { name: "Плут", hitDie: "d8" },
  { name: "Следопыт", hitDie: "d10" },
  { name: "Чародей", hitDie: "d10" },
  { name: "Альтернативный следопыт", hitDie: "d10" },
  { name: "Альтернативный монах", hitDie: "d10" },
  { name: "Альтернативный изобретатель", hitDie: "d8" },
  { name: "Магус", hitDie: "d10" },
  { name: "Кровавый охотник", hitDie: "d10" },
  { name: "Призыватель", hitDie: "d8" },
  { name: "Некромант", hitDie: "d8" }
];
const defaultCharacterClass = characterClasses[0].name;
const textFields = [
  { field: "name", label: "Имя" },
  { field: "subclass", label: "Подкласс" },
  { field: "race", label: "Раса" },
  { field: "background", label: "Предыстория" },
  { field: "route", label: "Путь" }
] as const;
const numberFields = [
  { field: "level", label: "Уровень" },
  { field: "hp", label: "HP" },
  { field: "temp_hp", label: "Временные HP" },
  { field: "armor_class", label: "КД (Armor Class)" },
  { field: "speed", label: "Скорость" },
  { field: "strength", label: "Сила (STR)" },
  { field: "dexterity", label: "Ловкость (DEX)" },
  { field: "constitution", label: "Телосложение (CON)" },
  { field: "intelligence", label: "Интеллект (INT)" },
  { field: "wisdom", label: "Мудрость (WIS)" },
  { field: "charisma", label: "Харизма (CHA)" },
  { field: "investigation", label: "Внимательность / Investigation" }
] as const;
const adminNumberFields = [
  { field: "level", label: "Уровень" },
  { field: "xp", label: "XP" },
  ...numberFields.filter(({ field }) => field !== "level")
] as const;
const blankCharacter = {
  name: "",
  class_name: defaultCharacterClass,
  subclass: "",
  race: "",
  background: "",
  route: "",
  game_created_at: GAME_EPOCH,
  level: 1,
  hp: 1,
  temp_hp: 0,
  armor_class: 10,
  speed: 30,
  strength: 10,
  dexterity: 10,
  constitution: 10,
  intelligence: 10,
  wisdom: 10,
  charisma: 10,
  investigation: 0
};
const maxCharacters = 10;
type CharacterFormState = typeof blankCharacter & Partial<Pick<
  Character,
  "id" | "xp" | "is_dead" | "user_id" | "owner_username" | "owner_email"
>>;

function playerCharacterUpdatePayload(form: CharacterFormState) {
  const {
    game_created_at: _gameCreatedAt,
    level: _level,
    xp: _xp,
    is_dead: _isDead,
    id: _id,
    user_id: _userId,
    owner_username: _ownerUsername,
    owner_email: _ownerEmail,
    ...payload
  } = form;
  return payload;
}

function apiErrorDetail(error: unknown, fallback: string) {
  const detail = (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
  return typeof detail === "string" ? detail : fallback;
}

function formatGameDate(value: string | undefined) {
  if (!value) return "-";
  const [year, month, day] = value.split("-");
  if (!year || !month || !day) return value;
  return `${day}.${month}.${year}`;
}

function abilityModifier(score: number) {
  return Math.floor((score - 10) / 2);
}

function signed(value: number) {
  return value >= 0 ? `+${value}` : String(value);
}

function classOptionsForValue(value: string) {
  if (!value || characterClasses.some((characterClass) => characterClass.name === value)) {
    return characterClasses;
  }
  return [{ name: value, hitDie: "-" }, ...characterClasses];
}

function hitDieForClass(value: string) {
  return classOptionsForValue(value).find((characterClass) => characterClass.name === value)?.hitDie ?? "-";
}

function useAuth() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!localStorage.getItem(TOKEN_KEY)) {
      setLoading(false);
      return;
    }
    api.get<User>("/me")
      .then((response) => setUser(response.data))
      .finally(() => setLoading(false));
  }, []);

  return { user, loading, setUser };
}

function Shell({ children, user }: { children: React.ReactNode; user: User | null }) {
  const navigate = useNavigate();

  function logout() {
    localStorage.removeItem(TOKEN_KEY);
    navigate("/login");
  }

  return (
    <div className="min-h-screen bg-[#101217] text-parchment">
      <header className="sticky top-0 z-10 border-b border-white/10 bg-[#101217]/95 backdrop-blur">
        <nav className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3">
          <Link to="/characters" className="text-lg font-bold text-ember">Эпоха Катастроф</Link>
          <div className="flex flex-wrap items-center gap-2">
            <Link className="btn-secondary" to="/"><UsersRound size={16} />Меню</Link>
            <Link className="btn-secondary" to="/characters"><UsersRound size={16} />Персонажи</Link>
            <Link className="btn-secondary" to="/shop"><ShoppingBag size={16} />Магазин</Link>
            <Link className="btn-secondary" to="/leaderboard"><Trophy size={16} />Лидеры</Link>
            <Link className="btn-secondary" to="/chat"><MessageSquare size={16} />Чат</Link>
            <Link className="btn-secondary" to="/profile"><UserRound size={16} />Профиль</Link>
            {user?.is_admin && <Link className="btn-secondary" to="/admin"><Shield size={16} />Админ</Link>}
            {user?.is_admin && <Link className="btn-secondary" to="/admin/shop-logs"><ScrollText size={16} />Логи</Link>}
            {user?.is_admin && <Link className="btn-secondary" to="/admin/transfer-logs"><ScrollText size={16} />Передачи</Link>}
            <button className="btn-secondary" onClick={logout}><LogOut size={16} />Выйти</button>
          </div>
        </nav>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6">{children}</main>
    </div>
  );
}

function HomePage() {
  const { user, loading } = useAuth();
  if (loading || !user) return <p>Загрузка...</p>;
  return (
    <div className="grid gap-4 md:grid-cols-[1fr_320px]">
      <section className="panel p-5">
        <h1 className="text-2xl font-bold text-ember">Главное меню</h1>
        <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <Link className="btn" to="/shop"><ShoppingBag size={18} />Shop</Link>
          <Link className="btn" to="/characters"><UsersRound size={18} />My Characters</Link>
          <Link className="btn" to="/characters/new"><Plus size={18} />Create Character</Link>
          <Link className="btn" to="/leaderboard"><Trophy size={18} />Таблица лидеров</Link>
          <Link className="btn" to="/chat"><MessageSquare size={18} />Чат</Link>
        </div>
      </section>
      <aside className="panel p-5">
        <h2 className="text-lg font-semibold text-ember">{user.username}</h2>
        <p className="mt-2 text-white/70">{user.email}</p>
        <p className="mt-3 text-sm text-white/80">Роль: {ROLE_LABELS[user.role ?? "player"]}</p>
        <p className="mt-4 text-xl font-semibold">Карма: {user.karma}</p>
      </aside>
    </div>
  );
}

function Protected({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const [, forceUpdate] = useState(0);

  useEffect(() => {
    function handleLogout() { forceUpdate(n => n + 1); }
    window.addEventListener("auth:logout", handleLogout);
    return () => window.removeEventListener("auth:logout", handleLogout);
  }, []);

  if (loading) return <div className="p-6 text-parchment">Загрузка...</div>;
  if (!localStorage.getItem(TOKEN_KEY)) return <Navigate to="/login" replace />;
  return <Shell user={user}>{children}</Shell>;
}

function Login() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    const body = new URLSearchParams({ username: email, password });
    try {
      const response = await api.post("/login", body);
      localStorage.setItem(TOKEN_KEY, response.data.access_token);
      navigate("/characters");
    } catch {
      setError("Не удалось войти");
    }
  }

  return <AuthPanel title="Вход" error={error} onSubmit={submit}>
    <input className="field" placeholder="email" value={email} onChange={(event) => setEmail(event.target.value)} />
    <input className="field" placeholder="password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
    <button className="btn" type="submit">Войти</button>
    <Link className="btn-secondary" to="/register">Перейти к регистрации</Link>
  </AuthPanel>;
}

function Register() {
  const navigate = useNavigate();
  const [form, setForm] = useState({ username: "", email: "", password: "" });
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      await api.post("/users", form);
      navigate("/login");
    } catch {
      setError("Не удалось создать аккаунт");
    }
  }

  return <AuthPanel title="Регистрация" error={error} onSubmit={submit}>
    <input className="field" placeholder="username" value={form.username} onChange={(event) => setForm({ ...form, username: event.target.value })} />
    <input className="field" placeholder="email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} />
    <input className="field" placeholder="password" type="password" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} />
    <button className="btn" type="submit">Создать аккаунт</button>
    <Link className="btn-secondary" to="/login">Войти</Link>
  </AuthPanel>;
}

function AuthPanel({ title, error, onSubmit, children }: { title: string; error: string; onSubmit: (event: FormEvent) => void; children: React.ReactNode }) {
  return (
    <div className="grid min-h-screen place-items-center bg-[#101217] px-4 text-parchment">
      <form className="panel flex w-full max-w-sm flex-col gap-3 p-6" onSubmit={onSubmit}>
        <h1 className="text-2xl font-bold text-ember">{title}</h1>
        {children}
        {error && <p className="text-sm text-red-300">{error}</p>}
      </form>
    </div>
  );
}

function ClassSelect({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return (
    <label className="field-label">
      <span>Класс</span>
      <select className="field" value={value} onChange={(event) => onChange(event.target.value)}>
        {classOptionsForValue(value).map((characterClass) => (
          <option key={characterClass.name} value={characterClass.name}>{characterClass.name}</option>
        ))}
      </select>
      <span className="text-xs text-white/55">Кость хитов: {hitDieForClass(value)}</span>
    </label>
  );
}

function CharactersPage() {
  const [characters, setCharacters] = useState<Character[]>([]);
  const [inventories, setInventories] = useState<Record<number, Inventory>>({});

  useEffect(() => {
    api.get<Character[]>("/characters").then(async (response) => {
      setCharacters(response.data);
      const pairs = await Promise.all(response.data.map(async (character) => {
        const inventory = await api.get<Inventory>(`/characters/${character.id}/inventory`);
        return [character.id, inventory.data] as const;
      }));
      setInventories(Object.fromEntries(pairs));
    });
  }, []);

  const characterLimitReached = characters.length >= maxCharacters;

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-ember">Мои персонажи</h1>
          <p className="text-sm text-white/65">Слоты: {characters.length}/{maxCharacters}</p>
        </div>
        {characterLimitReached ? (
          <button className="btn" disabled><Plus size={16} />Лимит персонажей</button>
        ) : (
          <Link className="btn" to="/characters/new"><Plus size={16} />Создать персонажа</Link>
        )}
      </div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {characters.map((character) => (
        <article className="panel p-4" key={character.id}>
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="text-xl font-semibold text-ember">{character.name}</h2>
              <p className="text-sm text-white/70">{character.race} {character.class_name} {character.subclass}</p>
            </div>
            <span className="rounded bg-white/10 px-2 py-1 text-sm">Ур. {character.level}</span>
          </div>
          <dl className="mt-4 grid grid-cols-3 gap-2 text-sm">
            <Stat label="XP" value={character.xp} />
            <Stat label="HP" value={character.hp} />
            <Stat label="КД" value={character.armor_class} />
            <Stat label="Золото" value={inventories[character.id]?.gold ?? 0} />
            <Stat label="Серебро" value={inventories[character.id]?.silver ?? 0} />
            <Stat label="Медь" value={inventories[character.id]?.copper ?? 0} />
          </dl>
          <p className="mt-3 text-sm text-white/60">{character.background || "Без предыстории"}</p>
          <div className="mt-4 flex gap-2">
            <Link className="btn" to={`/characters/${character.id}`}>Открыть персонажа</Link>
            <Link className="btn-secondary" to={`/characters/${character.id}/edit`}>Редактировать</Link>
            <Link className="btn-secondary" to={`/shop?character=${character.id}`}>Магазин</Link>
          </div>
        </article>
        ))}
      </div>
    </div>
  );
}

function CalendarPanel({ characterId }: { characterId: number }) {
  const [summary, setSummary] = useState<CalendarSummary | null>(null);
  const [form, setForm] = useState({ start_date: GAME_EPOCH, days: 1, reason: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editForm, setEditForm] = useState({ start_date: GAME_EPOCH, days: 1, reason: "" });
  const canManage = summary?.can_manage ?? false;

  useEffect(() => {
    let active = true;
    setLoading(true);
    api.get<CalendarSummary>(`/characters/${characterId}/calendar`)
      .then((response) => {
        if (!active) return;
        setSummary(response.data);
        setForm((current) => ({ ...current, start_date: response.data.created_at }));
      })
      .catch((loadError) => active && setError(apiErrorDetail(loadError, "Не удалось загрузить календарь")))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [characterId]);

  async function addEntry(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      const response = await api.post<CalendarSummary>(`/characters/${characterId}/calendar/downtime`, {
        start_date: form.start_date,
        days: Number(form.days),
        reason: form.reason
      });
      setSummary(response.data);
      setForm({ start_date: response.data.created_at, days: 1, reason: "" });
    } catch (addError) {
      setError(apiErrorDetail(addError, "Не удалось добавить запись"));
    }
  }

  async function removeEntry(entryId: number) {
    setError("");
    try {
      const response = await api.delete<CalendarSummary>(`/characters/${characterId}/calendar/downtime/${entryId}`);
      setSummary(response.data);
      if (editingId === entryId) setEditingId(null);
    } catch (removeError) {
      setError(apiErrorDetail(removeError, "Не удалось удалить запись"));
    }
  }

  function startEdit(entry: { id: number; start_date: string; days: number; reason: string }) {
    setError("");
    setEditingId(entry.id);
    setEditForm({ start_date: entry.start_date, days: entry.days, reason: entry.reason });
  }

  async function saveEdit(event: FormEvent) {
    event.preventDefault();
    if (editingId === null) return;
    setError("");
    try {
      const response = await api.patch<CalendarSummary>(`/characters/${characterId}/calendar/downtime/${editingId}`, {
        start_date: editForm.start_date,
        days: Number(editForm.days),
        reason: editForm.reason
      });
      setSummary(response.data);
      setEditingId(null);
    } catch (editError) {
      setError(apiErrorDetail(editError, "Не удалось изменить запись"));
    }
  }

  return (
    <section className="panel p-5">
      <div className="mb-4 flex items-center gap-2">
        <CalendarDays size={18} className="text-ember" />
        <h2 className="text-lg font-semibold text-ember">📅 Календарь персонажа</h2>
      </div>
      {loading && !summary ? (
        <p className="text-sm text-white/55">Загрузка...</p>
      ) : summary ? (
        <>
          <dl className="grid grid-cols-2 gap-3 md:grid-cols-3">
            <Stat label="Дата создания" value={formatGameDate(summary.created_at)} />
            <Stat label="Текущая игровая дата" value={formatGameDate(summary.current_date)} />
            <Stat label="Всего дней" value={summary.total_days} />
            <Stat label="Занятые дни" value={summary.busy_days} />
            <Stat label="Свободные дни" value={summary.free_days} />
          </dl>

          <form className="mt-5 grid gap-3 md:grid-cols-[150px_110px_1fr_auto]" onSubmit={addEntry}>
            <label className="field-label">
              <span>Дата начала</span>
              <input
                className="field"
                type="date"
                min={summary.created_at}
                max={summary.current_date}
                value={form.start_date}
                onChange={(event) => setForm({ ...form, start_date: event.target.value })}
              />
            </label>
            <label className="field-label">
              <span>Дней</span>
              <input
                className="field"
                type="number"
                min={1}
                value={form.days}
                onChange={(event) => setForm({ ...form, days: Number(event.target.value) })}
              />
            </label>
            <label className="field-label">
              <span>Причина</span>
              <input
                className="field"
                placeholder="Крафт, исследование, обучение..."
                value={form.reason}
                onChange={(event) => setForm({ ...form, reason: event.target.value })}
              />
            </label>
            <button className="btn self-end" type="submit"><Plus size={16} />Занять дни</button>
          </form>
          {error && <p className="mt-3 text-sm text-red-300">{error}</p>}

          <div className="mt-4 space-y-2">
            <h3 className="text-sm font-semibold text-white/70">Журнал занятых дней</h3>
            {!canManage && (
              <p className="text-xs text-white/45">Занятые дни нельзя удалять или редактировать. За исправлениями обратитесь к администратору.</p>
            )}
            {summary.entries.length === 0 ? (
              <p className="text-sm text-white/55">Занятых дней пока нет.</p>
            ) : (
              summary.entries.map((entry) => (
                <div className="rounded-md border border-white/10 px-3 py-2" key={entry.id}>
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <div className="font-semibold">
                        {formatGameDate(entry.start_date)} · {entry.days} дн.
                        {entry.source === "shop" && <span className="ml-2 rounded bg-amber-400/15 px-2 py-0.5 text-xs text-amber-200">магазин</span>}
                      </div>
                      <div className="text-sm text-white/60">{entry.reason || "Без описания"}</div>
                    </div>
                    {canManage && (
                      <div className="flex gap-2">
                        <button className="btn-secondary" onClick={() => startEdit(entry)} type="button"><Pencil size={16} />Изменить</button>
                        <button className="btn-secondary" onClick={() => removeEntry(entry.id)} type="button"><Trash2 size={16} />Удалить</button>
                      </div>
                    )}
                  </div>
                  {canManage && editingId === entry.id && (
                    <form className="mt-3 grid gap-3 md:grid-cols-[150px_110px_1fr_auto_auto]" onSubmit={saveEdit}>
                      <label className="field-label">
                        <span>Дата начала</span>
                        <input
                          className="field"
                          type="date"
                          min={summary.created_at}
                          max={summary.current_date}
                          value={editForm.start_date}
                          onChange={(event) => setEditForm({ ...editForm, start_date: event.target.value })}
                        />
                      </label>
                      <label className="field-label">
                        <span>Дней</span>
                        <input
                          className="field"
                          type="number"
                          min={1}
                          value={editForm.days}
                          onChange={(event) => setEditForm({ ...editForm, days: Number(event.target.value) })}
                        />
                      </label>
                      <label className="field-label">
                        <span>Причина</span>
                        <input
                          className="field"
                          value={editForm.reason}
                          onChange={(event) => setEditForm({ ...editForm, reason: event.target.value })}
                        />
                      </label>
                      <button className="btn self-end" type="submit"><Save size={16} />Сохранить</button>
                      <button className="btn-secondary self-end" type="button" onClick={() => setEditingId(null)}><X size={16} />Отмена</button>
                    </form>
                  )}
                </div>
              ))
            )}
          </div>
        </>
      ) : (
        <p className="text-sm text-red-300">{error || "Календарь недоступен"}</p>
      )}
    </section>
  );
}

function CharacterPage() {
  const { id: idParam } = useParams();
  const id = Number(idParam);
  const [character, setCharacter] = useState<Character | null>(null);
  const [inventory, setInventory] = useState<Inventory | null>(null);
  const [transferTargets, setTransferTargets] = useState<TransferTarget[]>([]);
  const [attacks, setAttacks] = useState<CharacterAttack[]>([]);
  const [attackForm, setAttackForm] = useState({ name: "", attack_bonus: 0, damage: "" });
  const [attackRoll, setAttackRoll] = useState<AttackRoll | null>(null);
  const [damageRoll, setDamageRoll] = useState<DamageRoll | null>(null);
  const [abilityRoll, setAbilityRoll] = useState<AbilityRoll | null>(null);
  const [savingThrowRoll, setSavingThrowRoll] = useState<SavingThrowRoll | null>(null);
  const [attackError, setAttackError] = useState("");

  useEffect(() => {
    Promise.all([
      api.get<Character[]>("/characters"),
      api.get<TransferTarget[]>("/characters/transfer-targets"),
      api.get<Inventory>(`/characters/${id}/inventory`),
      api.get<CharacterAttack[]>(`/characters/${id}/attacks`)
    ]).then(([charactersResponse, targetsResponse, inventoryResponse, attacksResponse]) => {
      setCharacter(charactersResponse.data.find((item) => item.id === id) ?? null);
      setTransferTargets(targetsResponse.data);
      setInventory(inventoryResponse.data);
      setAttacks(attacksResponse.data);
    });
  }, [id]);

  if (!character) return <p>Загрузка...</p>;
  const abilities = [
    { label: "Сила", short: "STR", field: "strength", value: character.strength },
    { label: "Ловкость", short: "DEX", field: "dexterity", value: character.dexterity },
    { label: "Телосложение", short: "CON", field: "constitution", value: character.constitution },
    { label: "Интеллект", short: "INT", field: "intelligence", value: character.intelligence },
    { label: "Мудрость", short: "WIS", field: "wisdom", value: character.wisdom },
    { label: "Харизма", short: "CHA", field: "charisma", value: character.charisma }
  ];

  async function createAttack(event: FormEvent) {
    event.preventDefault();
    setAttackError("");
    try {
      const response = await api.post<CharacterAttack>(`/characters/${id}/attacks`, attackForm);
      setAttacks((current) => [...current, response.data]);
      setAttackForm({ name: "", attack_bonus: 0, damage: "" });
    } catch (createError) {
      setAttackError(apiErrorDetail(createError, "Не удалось добавить атаку"));
    }
  }

  async function removeAttack(attack: CharacterAttack) {
    setAttackError("");
    try {
      await api.delete(`/characters/${id}/attacks/${attack.id}`);
      setAttacks((current) => current.filter((item) => item.id !== attack.id));
    } catch (removeError) {
      setAttackError(apiErrorDetail(removeError, "Не удалось удалить атаку"));
    }
  }

  async function rollAttack(attack: CharacterAttack) {
    setAttackError("");
    setDamageRoll(null);
    try {
      const response = await api.post<AttackRoll>(`/characters/${id}/attacks/${attack.id}/roll`);
      setAttackRoll(response.data);
    } catch (rollError) {
      setAttackError(apiErrorDetail(rollError, "Не удалось выполнить бросок атаки"));
    }
  }

  async function rollDamage(attack: CharacterAttack) {
    setAttackError("");
    setAttackRoll(null);
    try {
      const response = await api.post<DamageRoll>(`/characters/${id}/attacks/${attack.id}/roll-damage`);
      setDamageRoll(response.data);
    } catch (rollError) {
      setAttackError(apiErrorDetail(rollError, "Не удалось выполнить бросок урона"));
    }
  }

  async function rollAbility(ability: string) {
    setSavingThrowRoll(null);
    try {
      const response = await api.post<AbilityRoll>(`/characters/${id}/roll-ability/${ability}`);
      setAbilityRoll(response.data);
    } catch {
      // ignore
    }
  }

  async function rollSavingThrow(ability: string) {
    setAbilityRoll(null);
    try {
      const response = await api.post<SavingThrowRoll>(`/characters/${id}/roll-saving-throw/${ability}`);
      setSavingThrowRoll(response.data);
    } catch {
      // ignore
    }
  }

  return (
    <div className="space-y-4">
      <section className="panel p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs uppercase text-white/45">Лист персонажа</p>
            <h1 className="text-3xl font-bold text-ember">{character.name}</h1>
            <p className="mt-1 text-white/70">{character.class_name}{character.subclass ? ` / ${character.subclass}` : ""}</p>
          </div>
          <Link className="btn-secondary" to={`/characters/${id}/edit`}>Редактировать</Link>
        </div>
        <dl className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <Stat label="Раса" value={character.race || "-"} />
          <Stat label="Предыстория" value={character.background || "-"} />
          <Stat label="Путь" value={character.route || "-"} />
          <Stat label="Уровень" value={character.level} />
          <Stat label="XP" value={character.xp} />
        </dl>
      </section>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="space-y-4">
          <section className="panel p-5">
            <div className="mb-4 flex items-center gap-2">
              <Shield size={18} className="text-ember" />
              <h2 className="text-lg font-semibold text-ember">Боевой блок</h2>
            </div>
            <dl className="grid grid-cols-2 gap-3 md:grid-cols-5">
              <Stat label="HP" value={character.hp} />
              <Stat label="Временные HP" value={character.temp_hp} />
              <Stat label="КД" value={character.armor_class} />
              <Stat label="Скорость" value={`${character.speed} фт`} />
              <Stat label="Investigation" value={signed(character.investigation)} />
            </dl>
          </section>

          <CalendarPanel characterId={id} />

          <section className="panel p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-lg font-semibold text-ember">Характеристики</h2>
              {abilityRoll && (
                <div className="rounded-md border border-ember/40 px-3 py-2 text-sm">
                  <span className="font-semibold text-ember">{abilities.find((a) => a.field === abilityRoll.ability)?.label}</span>: d20 {signed(abilityRoll.modifier)} = <span className="font-bold text-ember">{abilityRoll.total}</span>
                </div>
              )}
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {abilities.map((ability) => (
                <AbilityCard key={ability.short} {...ability} onRoll={() => rollAbility(ability.field)} />
              ))}
            </div>
          </section>

          <section className="panel p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-lg font-semibold text-ember">Спасброски</h2>
              {savingThrowRoll && (
                <div className="rounded-md border border-ember/40 px-3 py-2 text-sm">
                  <span className="font-semibold text-ember">{abilities.find((a) => a.field === savingThrowRoll.ability)?.label}</span>: d20 {signed(savingThrowRoll.bonus)} = <span className="font-bold text-ember">{savingThrowRoll.total}</span>
                </div>
              )}
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {abilities.map((ability) => (
                <SavingThrowCard key={ability.short} label={ability.label} short={ability.short} value={ability.value} onRoll={() => rollSavingThrow(ability.field)} />
              ))}
            </div>
          </section>

          <section className="panel p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <Swords size={18} className="text-ember" />
                <h2 className="text-lg font-semibold text-ember">Атаки</h2>
              </div>
              {attackRoll && (
                <div className="rounded-md border border-ember/40 px-3 py-2 text-sm">
                  <span className="font-semibold text-ember">{attackRoll.name}</span>: d20 {signed(attackRoll.bonus)} = {attackRoll.total}
                </div>
              )}
              {damageRoll && (
                <div className="rounded-md border border-amber-400/40 px-3 py-2 text-sm">
                  <span className="font-semibold text-amber-300">{damageRoll.name}</span>: [{damageRoll.rolls.join(", ")}]{damageRoll.modifier !== 0 ? ` ${signed(damageRoll.modifier)}` : ""} = <span className="font-bold text-amber-300">{damageRoll.total}</span>
                </div>
              )}
            </div>
            <form className="mt-4 grid gap-3 md:grid-cols-[1fr_120px_1fr_auto]" onSubmit={createAttack}>
              <input className="field" placeholder="Название атаки" value={attackForm.name} onChange={(event) => setAttackForm({ ...attackForm, name: event.target.value })} />
              <input className="field" type="number" value={attackForm.attack_bonus} onChange={(event) => setAttackForm({ ...attackForm, attack_bonus: Number(event.target.value) })} />
              <input className="field" placeholder="Урон, например 1d8+3 рубящий" value={attackForm.damage} onChange={(event) => setAttackForm({ ...attackForm, damage: event.target.value })} />
              <button className="btn" disabled={!attackForm.name.trim()} type="submit"><Plus size={16} />Добавить</button>
            </form>
            {attackError && <p className="mt-3 text-sm text-red-300">{attackError}</p>}
            <div className="mt-4 space-y-3">
              {attacks.map((attack) => (
                <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-white/10 px-3 py-3" key={attack.id}>
                  <div>
                    <div className="font-semibold">{attack.name}</div>
                    <div className="text-sm text-white/60">Попадание: {signed(attack.attack_bonus)} · Урон: {attack.damage || "-"}</div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button className="btn-secondary" onClick={() => rollAttack(attack)}><Dice5 size={16} />Бросить атаку</button>
                    {attack.damage && <button className="btn-secondary" onClick={() => rollDamage(attack)}><Dice5 size={16} />Бросить урон</button>}
                    <button className="btn-secondary" onClick={() => removeAttack(attack)}><Trash2 size={16} />Удалить</button>
                  </div>
                </div>
              ))}
              {attacks.length === 0 && <p className="text-sm text-white/55">Атаки пока не добавлены.</p>}
            </div>
          </section>
        </div>

        <InventoryPanel inventory={inventory} onChange={setInventory} characterId={id} transferTargets={transferTargets} />
      </div>
    </div>
  );
}

function AbilityCard({ label, short, value, onRoll }: { label: string; short: string; value: number; onRoll?: () => void }) {
  const modifier = abilityModifier(value);
  return (
    <button
      className="ability-card text-left w-full"
      onClick={onRoll}
      title={onRoll ? `Бросить d20 + ${signed(modifier)}` : undefined}
      type="button"
    >
      <div>
        <p className="text-xs uppercase text-white/45">{short}</p>
        <h3 className="font-semibold text-ember">{label}</h3>
      </div>
      <div className="text-right">
        <div className="text-3xl font-bold">{value}</div>
        <div className="text-lg font-semibold text-white/75">{signed(modifier)}</div>
      </div>
    </button>
  );
}

function SavingThrowCard({ label, short, value, onRoll }: { label: string; short: string; value: number; onRoll?: () => void }) {
  const modifier = abilityModifier(value);
  return (
    <button
      className="ability-card text-left w-full"
      onClick={onRoll}
      title={onRoll ? `Спасбросок d20 + ${signed(modifier)}` : undefined}
      type="button"
    >
      <div>
        <p className="text-xs uppercase text-white/45">{short}</p>
        <h3 className="font-semibold text-ember">{label}</h3>
      </div>
      <div className="text-right">
        <div className="text-lg font-semibold text-white/75">{signed(modifier)}</div>
      </div>
    </button>
  );
}

function CharacterFormPage({ edit = false }: { edit?: boolean }) {
  const navigate = useNavigate();
  const { id: idParam } = useParams();
  const id = Number(idParam);
  const [form, setForm] = useState<CharacterFormState>(blankCharacter);
  const [error, setError] = useState("");
  const visibleNumberFields = edit
    ? numberFields.filter(({ field }) => field !== "level")
    : numberFields;

  useEffect(() => {
    if (!edit) return;
    api.get<Character[]>("/characters").then((response) => {
      const character = response.data.find((item) => item.id === id);
      if (character) {
        setForm({
          ...blankCharacter,
          ...character,
          game_created_at: character.game_created_at ?? blankCharacter.game_created_at
        });
      }
    });
  }, [edit, id]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      if (edit) {
        await api.patch(`/characters/${id}`, playerCharacterUpdatePayload(form));
        navigate(`/characters/${id}`);
      } else {
        await api.post("/characters", form);
        navigate("/characters");
      }
    } catch (error) {
      setError(apiErrorDetail(error, "Не удалось сохранить персонажа"));
    }
  }

  return (
    <form className="panel grid gap-3 p-5 md:grid-cols-2" onSubmit={submit}>
      <h1 className="text-xl font-bold text-ember md:col-span-2">{edit ? "Редактировать персонажа" : "Создать персонажа"}</h1>
      <div className="md:col-span-2">
        <ClassSelect value={form.class_name} onChange={(value) => setForm({ ...form, class_name: value })} />
      </div>
      <label className="field-label md:col-span-2">
        <span>📅 Дата создания персонажа</span>
        <input
          className="field"
          type="date"
          min={GAME_EPOCH}
          value={form.game_created_at ?? GAME_EPOCH}
          disabled={edit}
          onChange={(event) => setForm({ ...form, game_created_at: event.target.value })}
        />
        <span className="text-xs text-white/45">
          {edit
            ? "Дату создания нельзя изменить после создания персонажа."
            : `Начало игрового мира — ${formatGameDate(GAME_EPOCH)}. Эта дата используется для подсчёта свободных дней.`}
        </span>
      </label>
      {textFields.map(({ field, label }) => (
        <label className="field-label" key={field}>
          <span>{label}</span>
          <input className="field" value={form[field]} onChange={(event) => setForm({ ...form, [field]: event.target.value })} />
        </label>
      ))}
      {visibleNumberFields.map(({ field, label }) => (
        <label className="field-label" key={field}>
          <span>{label}</span>
          <input className="field" type="number" value={form[field]} onChange={(event) => setForm({ ...form, [field]: Number(event.target.value) })} />
        </label>
      ))}
      {error && <p className="text-sm text-red-300 md:col-span-2">{error}</p>}
      <button className="btn md:col-span-2" type="submit">Сохранить</button>
    </form>
  );
}

function InventoryPanel({ inventory, onChange, characterId, transferTargets }: { inventory: Inventory | null; onChange: (inventory: Inventory) => void; characterId: number; transferTargets: TransferTarget[] }) {
  const recipients = transferTargets.filter((character) => character.id !== characterId);
  const [currencyTransfer, setCurrencyTransfer] = useState({ recipient_character_id: "", gold: 0, silver: 0, copper: 0 });
  const [itemRecipients, setItemRecipients] = useState<Record<number, string>>({});
  const [notesDraft, setNotesDraft] = useState("");
  const [notesSaved, setNotesSaved] = useState(false);
  const [error, setError] = useState("");

  async function remove(item: InventoryItem) {
    const response = await api.delete<Inventory>(`/characters/${characterId}/inventory/items/${item.id}`);
    onChange(response.data);
  }

  async function transferCurrency(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      const response = await api.post<Inventory>(`/characters/${characterId}/inventory/currency/transfer`, {
        ...currencyTransfer,
        recipient_character_id: Number(currencyTransfer.recipient_character_id)
      });
      onChange(response.data);
      setCurrencyTransfer({ recipient_character_id: currencyTransfer.recipient_character_id, gold: 0, silver: 0, copper: 0 });
    } catch (transferError) {
      setError(apiErrorDetail(transferError, "Не удалось передать валюту"));
    }
  }

  async function transferItem(item: InventoryItem) {
    const recipientId = itemRecipients[item.id];
    if (!recipientId) return;
    setError("");
    try {
      const response = await api.post<Inventory>(`/characters/${characterId}/inventory/items/transfer`, {
        recipient_character_id: Number(recipientId),
        item_id: item.id
      });
      onChange(response.data);
    } catch (transferError) {
      setError(apiErrorDetail(transferError, "Не удалось передать предмет"));
    }
  }

  async function saveNotes() {
    setError("");
    setNotesSaved(false);
    try {
      const response = await api.patch<Inventory>(`/characters/${characterId}/inventory/notes`, { notes: notesDraft });
      onChange(response.data);
      setNotesSaved(true);
    } catch (notesError) {
      setError(apiErrorDetail(notesError, "Не удалось сохранить заметки"));
    }
  }

  useEffect(() => {
    if (!currencyTransfer.recipient_character_id && recipients[0]) {
      setCurrencyTransfer((current) => ({ ...current, recipient_character_id: String(recipients[0].id) }));
    }
  }, [currencyTransfer.recipient_character_id, recipients]);

  useEffect(() => {
    setNotesDraft(inventory?.notes ?? "");
    setNotesSaved(false);
  }, [inventory?.id, inventory?.notes]);

  return (
    <aside className="panel p-5">
      <h2 className="text-lg font-semibold text-ember">Инвентарь</h2>
      <p className="mt-1 text-sm text-white/70">{inventory?.gold ?? 0} зол. / {inventory?.silver ?? 0} сер. / {inventory?.copper ?? 0} мед.</p>
      <div className="mt-4">
        <label className="field-label">
          <span>Заметки</span>
          <textarea className="field min-h-32 resize-y" value={notesDraft} onChange={(event) => {
            setNotesSaved(false);
            setNotesDraft(event.target.value);
          }} />
        </label>
        <div className="mt-2 flex items-center gap-3">
          <button className="btn-secondary" onClick={saveNotes}><Save size={16} />Сохранить заметки</button>
          {notesSaved && <span className="text-sm text-emerald-200">Сохранено</span>}
        </div>
      </div>
      <form className="mt-4 rounded-md border border-white/10 p-3" onSubmit={transferCurrency}>
        <h3 className="font-semibold text-ember">Передать валюту</h3>
        <div className="mt-3 grid grid-cols-3 gap-2">
          {(["gold", "silver", "copper"] as const).map((field) => (
            <input
              className="field"
              key={field}
              min={0}
              type="number"
              value={currencyTransfer[field]}
              onChange={(event) => setCurrencyTransfer({ ...currencyTransfer, [field]: Number(event.target.value) })}
            />
          ))}
        </div>
        <select className="field mt-2" value={currencyTransfer.recipient_character_id} onChange={(event) => setCurrencyTransfer({ ...currencyTransfer, recipient_character_id: event.target.value })}>
          {recipients.map((character) => <option key={character.id} value={character.id}>{character.name} · {character.owner_username}</option>)}
        </select>
        <button className="btn mt-2 w-full" disabled={!currencyTransfer.recipient_character_id}>Передать</button>
      </form>
      {error && <p className="mt-3 text-sm text-red-300">{error}</p>}
      <div className="mt-4 space-y-3">
        {inventory?.items.map((item) => (
          <div className="rounded-md border border-white/10 p-3" key={item.id}>
            <div className="font-semibold">{item.name}</div>
            <div className="text-sm text-white/60">{item.rarity} · {item.is_consumable ? "расходуемый" : "постоянный"}</div>
            <div className="mt-3 flex flex-wrap gap-2">
              <Link className="btn-secondary" to={`/shop?mode=sell&character=${characterId}&item=${item.id}`}>Продать</Link>
              <button className="btn-secondary" onClick={() => remove(item)}>Удалить</button>
              <select className="field min-w-0 flex-1" value={itemRecipients[item.id] ?? ""} onChange={(event) => setItemRecipients({ ...itemRecipients, [item.id]: event.target.value })}>
                <option value="">Кому передать</option>
                {recipients.map((character) => <option key={character.id} value={character.id}>{character.name} · {character.owner_username}</option>)}
              </select>
              <button className="btn-secondary" disabled={!itemRecipients[item.id]} onClick={() => transferItem(item)}>Передать</button>
            </div>
          </div>
        ))}
      </div>
    </aside>
  );
}

function ShopPage() {
  const [characters, setCharacters] = useState<Character[]>([]);
  const [characterId, setCharacterId] = useState("");
  const [mode, setMode] = useState<"buy" | "sell">(() => new URLSearchParams(window.location.search).get("mode") === "sell" ? "sell" : "buy");
  const [inventory, setInventory] = useState<Inventory | null>(null);
  const [form, setForm] = useState({ magic_item_id: "", item_name: "", rarity: "Обычный", is_consumable: false, item_id: "", searcher_type: "hireling", hireling_level: "Плохой" });
  const [magicItems, setMagicItems] = useState<MagicItem[]>([]);
  const [magicItemSearch, setMagicItemSearch] = useState("");
  const [magicItemRarity, setMagicItemRarity] = useState("");
  const [magicItemType, setMagicItemType] = useState("");
  const [magicItemsLoading, setMagicItemsLoading] = useState(false);
  const [result, setResult] = useState<ShopResult | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get<Character[]>("/characters").then((response) => {
      setCharacters(response.data);
      const selected = new URLSearchParams(window.location.search).get("character");
      setCharacterId(selected ?? String(response.data[0]?.id ?? ""));
    });
  }, []);

  useEffect(() => {
    if (!characterId) return;
    api.get<Inventory>(`/characters/${characterId}/inventory`).then((response) => {
      setInventory(response.data);
      const selectedItem = new URLSearchParams(window.location.search).get("item");
      const fallbackItem = response.data.items[0]?.id;
      setForm((current) => ({
        ...current,
        item_id: selectedItem ?? (fallbackItem ? String(fallbackItem) : "")
      }));
    });
  }, [characterId]);

  useEffect(() => {
    if (mode !== "buy") return;

    const handle = window.setTimeout(() => {
      setMagicItemsLoading(true);
      api.get<MagicItem[]>("/shop/magic-items", {
        params: {
          search: magicItemSearch || undefined,
          rarity: magicItemRarity || undefined,
          item_type: magicItemType || undefined,
          limit: 100
        }
      })
        .then((response) => setMagicItems(response.data))
        .catch(() => setMagicItems([]))
        .finally(() => setMagicItemsLoading(false));
    }, 150);

    return () => window.clearTimeout(handle);
  }, [mode, magicItemSearch, magicItemRarity, magicItemType]);

  function selectMagicItem(itemId: string) {
    const item = magicItems.find((magicItem) => magicItem.id === itemId);
    if (!item) {
      setForm((current) => ({ ...current, magic_item_id: "" }));
      return;
    }

    setForm((current) => ({
      ...current,
      magic_item_id: item.id,
      item_name: item.name,
      rarity: item.rarity,
      is_consumable: item.is_consumable
    }));
  }

  async function performSearch() {
    setError("");
    try {
      const payload = mode === "buy"
        ? {
            mode,
            magic_item_id: form.magic_item_id || undefined,
            item_name: form.item_name,
            rarity: form.rarity,
            is_consumable: form.is_consumable,
            searcher_type: form.searcher_type,
            hireling_level: form.hireling_level
          }
        : {
            mode,
            item_id: Number(form.item_id),
            searcher_type: form.searcher_type,
            hireling_level: form.hireling_level
          };
      const response = await api.post<ShopResult>(`/characters/${characterId}/shop/search`, payload);
      setResult(response.data);
      setInventory(response.data.inventory);
    } catch (searchError) {
      setError(apiErrorDetail(searchError, "Поиск не выполнен"));
    }
  }

  async function searchShop(event: FormEvent) {
    event.preventDefault();
    await performSearch();
  }

  async function confirmResult() {
    if (!result?.quote_id) return;
    setError("");
    try {
      const endpoint = result.mode === "buy" ? "buy" : "sell";
      const response = await api.post<ShopResult>(`/characters/${characterId}/shop/${endpoint}`, { quote_id: result.quote_id });
      setResult(response.data);
      setInventory(response.data.inventory);
      if (response.data.mode === "sell") {
        setForm((current) => ({
          ...current,
          item_id: String(response.data.inventory.items[0]?.id ?? "")
        }));
      }
    } catch {
      setError("Не удалось подтвердить сделку");
    }
  }

  function switchMode(nextMode: "buy" | "sell") {
    setMode(nextMode);
    setResult(null);
    setError("");
    if (nextMode === "sell") {
      setForm((current) => ({
        ...current,
        item_id: current.item_id || String(inventory?.items[0]?.id ?? "")
      }));
    }
  }

  const selectedCharacter = characters.find((character) => String(character.id) === characterId);
  const selectedItem = inventory?.items.find((item) => String(item.id) === form.item_id);
  const selectedMagicItem = magicItems.find((item) => item.id === form.magic_item_id);
  const canSearch = Boolean(characterId) && (mode === "buy" ? Boolean(form.magic_item_id || form.item_name.trim()) : Boolean(form.item_id));

  return (
    <div className="grid gap-4 lg:grid-cols-[420px_1fr]">
      <form className="panel flex flex-col gap-4 p-5" onSubmit={searchShop}>
        <h1 className="text-xl font-bold text-ember">Магазин</h1>
        <div className="grid grid-cols-2 gap-2">
          <button type="button" className={mode === "buy" ? "mode-tab-active" : "mode-tab"} onClick={() => switchMode("buy")}>Купить</button>
          <button type="button" className={mode === "sell" ? "mode-tab-active" : "mode-tab"} onClick={() => switchMode("sell")}>Продать</button>
        </div>
        <select className="field" value={characterId} onChange={(event) => setCharacterId(event.target.value)}>
          {characters.map((character) => <option key={character.id} value={character.id}>{character.name}</option>)}
        </select>
        <p className="text-sm text-white/70">{selectedCharacter?.name ?? "Персонаж"}: {inventory?.gold ?? 0} зм / {inventory?.silver ?? 0} см / {inventory?.copper ?? 0} мм</p>
        {mode === "buy" ? (
          <>
            <label className="field-label">
              <span>Поиск в базе предметов</span>
              <input className="field" value={magicItemSearch} onChange={(event) => setMagicItemSearch(event.target.value)} />
            </label>
            <div className="grid gap-2 sm:grid-cols-2">
              <label className="field-label">
                <span>Фильтр редкости</span>
                <select className="field" value={magicItemRarity} onChange={(event) => setMagicItemRarity(event.target.value)}>
                  <option value="">Все</option>
                  {rarities.map((rarity) => <option key={rarity} value={rarity}>{rarity}</option>)}
                </select>
              </label>
              <label className="field-label">
                <span>Тип</span>
                <input className="field" value={magicItemType} onChange={(event) => setMagicItemType(event.target.value)} />
              </label>
            </div>
            <label className="field-label">
              <span>Предмет из базы</span>
              <select className="field min-h-48" size={8} value={form.magic_item_id} onChange={(event) => selectMagicItem(event.target.value)}>
                <option value="">Ручной ввод</option>
                {magicItems.map((item) => (
                  <option key={item.id} value={item.id}>{item.name} · {item.rarity} · {item.item_type}</option>
                ))}
              </select>
            </label>
            {magicItemsLoading && <p className="text-sm text-white/55">Загрузка предметов...</p>}
            {selectedMagicItem && (
              <div className="rounded-md border border-white/10 bg-black/25 p-3 text-sm text-white/70">
                <p className="font-semibold text-parchment">{selectedMagicItem.name}</p>
                <p>{selectedMagicItem.rarity} · {selectedMagicItem.item_type}{selectedMagicItem.is_consumable ? " · расходуемый" : ""}</p>
                {(selectedMagicItem.source || selectedMagicItem.page || selectedMagicItem.tier) && (
                  <p>
                    {[selectedMagicItem.source, selectedMagicItem.page ? `стр. ${selectedMagicItem.page}` : "", selectedMagicItem.tier].filter(Boolean).join(" · ")}
                  </p>
                )}
                {selectedMagicItem.entries[0] && <p className="mt-2 max-h-24 overflow-hidden text-white/60">{selectedMagicItem.entries[0]}</p>}
              </div>
            )}
            <label className="field-label">
              <span>Название предмета</span>
              <input className="field" value={form.item_name} onChange={(event) => setForm({ ...form, magic_item_id: "", item_name: event.target.value })} />
            </label>
            <label className="field-label">
              <span>Редкость</span>
              <select className="field" value={form.rarity} onChange={(event) => setForm({ ...form, magic_item_id: "", rarity: event.target.value })}>{rarities.map((rarity) => <option key={rarity}>{rarity}</option>)}</select>
            </label>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.is_consumable} onChange={(event) => setForm({ ...form, magic_item_id: "", is_consumable: event.target.checked })} />Расходуемый</label>
          </>
        ) : (
          <label className="field-label">
            <span>Предмет из инвентаря</span>
            <select className="field" value={form.item_id} onChange={(event) => setForm({ ...form, item_id: event.target.value })}>
              {inventory?.items.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.rarity}</option>)}
            </select>
          </label>
        )}
        <div className="grid grid-cols-2 gap-2">
          <button type="button" className={form.searcher_type === "character" ? "mode-tab-active" : "mode-tab"} onClick={() => setForm({ ...form, searcher_type: "character" })}>Персонаж</button>
          <button type="button" className={form.searcher_type === "hireling" ? "mode-tab-active" : "mode-tab"} onClick={() => setForm({ ...form, searcher_type: "hireling" })}>Наёмник</button>
        </div>
        <div className="grid gap-2 sm:grid-cols-2">
          {hirelings.map((hireling) => (
            <button
              className={form.hireling_level === hireling.level ? "hireling-option-active" : "hireling-option"}
              disabled={form.searcher_type !== "hireling"}
              key={hireling.level}
              onClick={() => setForm({ ...form, hireling_level: hireling.level })}
              type="button"
            >
              <span className="font-semibold">{hireling.level}</span>
              <span>Бонус: +{hireling.bonus}</span>
              <span>Стоимость: {hireling.cost} зм/день</span>
            </button>
          ))}
        </div>
        {mode === "sell" && !selectedItem && <p className="text-sm text-red-300">У персонажа нет предметов для продажи.</p>}
        {error && <p className="text-sm text-red-300">{error}</p>}
        <button className="btn" disabled={!canSearch}><Search size={16} />{mode === "buy" ? "Найти продавца" : "Найти покупателя"}</button>
      </form>
      <ResultPanel result={result} onConfirm={confirmResult} onContinue={performSearch} />
    </div>
  );
}

function ResultPanel({ result, onConfirm, onContinue }: { result: ShopResult | null; onConfirm: () => void; onContinue: () => void }) {
  if (!result) return <section className="panel p-5 text-white/60">Результат поиска появится здесь.</section>;
  const action = result.mode === "buy" ? "Купить предмет" : "Продать предмет";
  return (
    <section className="panel p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-ember">{result.success ? "Сделка найдена" : "Сделка не найдена"}</h2>
          <p className="text-sm text-white/65">{result.item_name} · {result.rarity} · {result.mode === "buy" ? "покупка" : "продажа"}</p>
        </div>
        {result.is_consumed && <span className="rounded-md border border-emerald-400/40 px-2 py-1 text-sm text-emerald-200">Сделка завершена</span>}
      </div>
      <dl className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Бросок" value={result.search_roll} />
        <Stat label="Модификатор" value={result.modifier >= 0 ? `+${result.modifier}` : result.modifier} />
        <Stat label="Итог" value={result.total_roll} />
        <Stat label="DC" value={result.dc} />
        <Stat label="Дни" value={result.days} />
        <Stat label="Бросок цены" value={result.price_roll ?? "-"} />
        <Stat label="Множитель" value={result.multiplier ? `x${result.multiplier.toFixed(2)}` : "-"} />
        <Stat label="Цена, зм" value={result.item_price ?? "-"} />
        <Stat label="Наёмник, зм" value={result.hireling_cost} />
        <Stat label="Итого, зм" value={result.total_cost ?? "-"} />
      </dl>
      <div className="mt-5 flex flex-wrap gap-2">
        {result.success && !result.is_consumed && <button className="btn" onClick={onConfirm}><Check size={16} />{action}</button>}
        {!result.is_consumed && <button className="btn-secondary" onClick={onContinue}><RefreshCw size={16} />Продолжить поиск</button>}
      </div>
    </section>
  );
}

function ProfilePage() {
  const { user, loading } = useAuth();
  if (loading || !user) return <p>Загрузка...</p>;
  return <section className="panel max-w-xl p-5"><h1 className="text-xl font-bold text-ember">{user.username}</h1><p>{user.email}</p><p className="mt-2">Карма: {user.karma}</p></section>;
}

function LeaderboardPage() {
  const [entries, setEntries] = useState<LeaderboardEntry[]>([]);

  useEffect(() => {
    api.get<LeaderboardEntry[]>("/leaderboard").then((response) => setEntries(response.data));
  }, []);

  return (
    <section className="panel p-5">
      <div className="mb-5 flex items-center gap-2">
        <Trophy size={20} className="text-ember" />
        <h1 className="text-xl font-bold text-ember">Таблица лидеров</h1>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[520px] text-left text-sm">
          <thead className="text-xs uppercase text-white/45">
            <tr>
              <th className="py-2 pr-3">Место</th>
              <th className="py-2 pr-3">Пользователь</th>
              <th className="py-2 pr-3">Карма</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry) => (
              <tr className="border-t border-white/10" key={entry.id}>
                <td className="py-3 pr-3 font-semibold text-ember">{entry.rank}</td>
                <td className="py-3 pr-3">{entry.username}</td>
                <td className="py-3 pr-3">{entry.karma}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

const CHAT_PAGE_SIZE = 50;

function ChatPage() {
  const [channel, setChannel] = useState<"general" | "rolls">("general");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [content, setContent] = useState("");
  const [error, setError] = useState("");
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);
  const pendingScrollToBottom = useRef(false);

  async function loadMessages(nextChannel = channel) {
    pendingScrollToBottom.current = true;
    try {
      const response = await api.get<ChatMessage[]>("/chat/messages", {
        params: { channel: nextChannel, limit: CHAT_PAGE_SIZE }
      });
      setMessages(response.data);
      setHasMore(response.data.length === CHAT_PAGE_SIZE);
    } catch (loadError) {
      pendingScrollToBottom.current = false;
      setError(apiErrorDetail(loadError, "Не удалось загрузить чат"));
    }
  }

  useEffect(() => {
    setError("");
    setHasMore(false);
    loadMessages(channel);
  }, [channel]);

  useLayoutEffect(() => {
    // Only scroll once the freshly loaded messages have actually rendered.
    // The initial mount renders with an empty list, so guarding on
    // messages.length keeps the pending flag set until real content arrives
    // (otherwise the empty render would consume it and the view would stay
    // pinned at the oldest message).
    if (pendingScrollToBottom.current && listRef.current && messages.length > 0) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
      pendingScrollToBottom.current = false;
    }
  }, [messages, channel]);

  async function loadOlderMessages() {
    if (!messages.length) return;
    setLoadingMore(true);
    try {
      const oldestId = messages[0].id;
      const response = await api.get<ChatMessage[]>("/chat/messages", {
        params: { channel, limit: CHAT_PAGE_SIZE, before_id: oldestId }
      });
      const previousScrollHeight = listRef.current?.scrollHeight ?? 0;
      setMessages((current) => [...response.data, ...current]);
      setHasMore(response.data.length === CHAT_PAGE_SIZE);
      requestAnimationFrame(() => {
        if (listRef.current) {
          listRef.current.scrollTop = listRef.current.scrollHeight - previousScrollHeight;
        }
      });
    } catch (loadError) {
      setError(apiErrorDetail(loadError, "Не удалось загрузить сообщения"));
    } finally {
      setLoadingMore(false);
    }
  }

  async function sendMessage(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      const response = await api.post<ChatMessage>("/chat/messages", { content });
      setContent("");
      if (response.data.channel !== channel) {
        setChannel(response.data.channel);
      } else {
        setMessages((current) => [...current, response.data]);
        requestAnimationFrame(() => {
          if (listRef.current) {
            listRef.current.scrollTop = listRef.current.scrollHeight;
          }
        });
      }
    } catch (sendError) {
      setError(apiErrorDetail(sendError, "Не удалось отправить сообщение"));
    }
  }

  return (
    <section className="panel flex h-[calc(100vh-7rem)] flex-col p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <MessageSquare size={20} className="text-ember" />
          <h1 className="text-xl font-bold text-ember">Чат</h1>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <button className={channel === "general" ? "mode-tab-active" : "mode-tab"} onClick={() => setChannel("general")}>Общий чат</button>
          <button className={channel === "rolls" ? "mode-tab-active" : "mode-tab"} onClick={() => setChannel("rolls")}>Броски</button>
        </div>
      </div>

      <div ref={listRef} className="mt-5 min-h-0 flex-1 space-y-3 overflow-y-auto rounded-md border border-white/10 p-3">
        {hasMore && (
          <div className="flex justify-center pb-2">
            <button className="btn-secondary" onClick={loadOlderMessages} disabled={loadingMore}>
              {loadingMore ? "Загрузка..." : "Загрузить ещё"}
            </button>
          </div>
        )}
        {messages.map((message) => (
          <article className="rounded-md bg-black/25 p-3" key={message.id}>
            <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
              <span className="font-semibold text-ember">{message.username}</span>
              <span className="text-white/45">{new Date(message.created_at).toLocaleString("ru-RU")}</span>
            </div>
            {message.channel === "rolls" ? (
              <div className="mt-2 text-sm text-white/80">
                <p className="whitespace-pre-wrap">{message.content}</p>
                {message.formula && (
                  <p className="mt-2 text-white/60">Формула: {message.formula} · Результаты: [{message.rolls?.join(", ")}] · Итого: {message.total}</p>
                )}
              </div>
            ) : (
              <p className="mt-2 whitespace-pre-wrap text-sm text-white/80">{message.content}</p>
            )}
          </article>
        ))}
        {messages.length === 0 && <p className="text-sm text-white/55">Сообщений пока нет.</p>}
      </div>

      <form className="mt-4 grid gap-2 md:grid-cols-[1fr_auto]" onSubmit={sendMessage}>
        <input className="field" placeholder={channel === "rolls" ? "/r 1d20" : "Сообщение или /r 2d6"} value={content} onChange={(event) => setContent(event.target.value)} />
        <button className="btn" disabled={!content.trim()}><Send size={16} />Отправить</button>
      </form>
      {error && <p className="mt-3 text-sm text-red-300">{error}</p>}
    </section>
  );
}

const ROLE_OPTIONS: UserRole[] = ["owner", "head_admin", "admin", "player"];

// Roles that a head administrator is allowed to assign. Owners may assign any
// role, while head admins can only manage admins and players.
const HEAD_ADMIN_ASSIGNABLE_ROLES: UserRole[] = ["admin", "player"];

function AdminPage() {
  const { user } = useAuth();
  const [characters, setCharacters] = useState<Character[]>([]);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [selected, setSelected] = useState("");
  const [amount, setAmount] = useState(1);
  const [karmaUserId, setKarmaUserId] = useState("");
  const [karmaAmount, setKarmaAmount] = useState(1);
  const [item, setItem] = useState({ name: "", rarity: "Обычный", is_consumable: false });
  const [roleError, setRoleError] = useState("");

  const selectedCharacter = useMemo(() => characters.find((character) => String(character.id) === selected), [characters, selected]);
  const selectedUser = useMemo(() => users.find((user) => String(user.id) === karmaUserId), [users, karmaUserId]);

  function load() {
    Promise.all([
      api.get<Character[]>("/admin/characters"),
      api.get<AdminUser[]>("/admin/users")
    ]).then(([characterResponse, userResponse]) => {
      setCharacters(characterResponse.data);
      setSelected((current) => characterResponse.data.some((character) => String(character.id) === current) ? current : String(characterResponse.data[0]?.id ?? ""));
      setUsers(userResponse.data);
      setKarmaUserId((current) => userResponse.data.some((user) => String(user.id) === current) ? current : String(userResponse.data[0]?.id ?? ""));
    });
  }

  useEffect(load, []);

  async function action(path: string, body?: unknown) {
    await api.post(`/admin/characters/${selected}/${path}`, body ?? {});
    load();
  }

  async function applyKarma() {
    await api.post(`/admin/users/${karmaUserId}/karma`, { amount: karmaAmount });
    load();
  }

  async function changeRole(userId: number, role: UserRole) {
    setRoleError("");
    try {
      await api.post(`/admin/users/${userId}/role`, { role });
      load();
    } catch (error) {
      setRoleError(apiErrorDetail(error, "Не удалось изменить роль"));
    }
  }

  const canManageRoles = Boolean(user?.is_owner || user?.is_head_admin);

  // Head admins may not touch owners or other head admins, and they may never
  // grant the owner or head-admin roles. Owners have unrestricted control.
  function canEditRole(row: AdminUser): boolean {
    if (row.id === user?.id) return false;
    if (user?.is_owner) return true;
    return !row.is_owner && !row.is_head_admin;
  }

  function roleOptionsFor(row: AdminUser): UserRole[] {
    const assignable = user?.is_owner ? ROLE_OPTIONS : HEAD_ADMIN_ASSIGNABLE_ROLES;
    // Always keep the row's current role visible in the dropdown, even when it
    // is one the current actor is not allowed to assign.
    return assignable.includes(row.role) ? assignable : [row.role, ...assignable];
  }

  return (
    <div className="grid gap-4 xl:grid-cols-[360px_1fr]">
      <div className="space-y-4">
        <section className="panel flex flex-col gap-3 p-5">
          <div className="flex items-center justify-between gap-3">
            <h1 className="text-xl font-bold text-ember">Админка мастера</h1>
            <Link className="btn-secondary" to="/admin/shop-logs"><ScrollText size={16} />Магазин</Link>
            <Link className="btn-secondary" to="/admin/transfer-logs"><ScrollText size={16} />Передачи</Link>
          </div>
          <label className="field-label">
            <span>Персонаж</span>
            <select className="field" value={selected} onChange={(event) => setSelected(event.target.value)}>
              {characters.map((character) => <option value={character.id} key={character.id}>{character.name} · {character.owner_username}</option>)}
            </select>
          </label>
          <label className="field-label">
            <span>Изменение</span>
            <input className="field" type="number" value={amount} onChange={(event) => setAmount(Number(event.target.value))} />
          </label>
          <button className="btn" onClick={() => action("xp", { amount })}>Применить XP</button>
          <button className="btn" onClick={() => action("gold", { amount })}>Применить золото</button>
          <button className="btn-secondary" onClick={() => action("revive")}>Воскресить персонажа</button>
          <div className="mt-2 border-t border-white/10 pt-3">
            <h2 className="text-lg font-semibold text-ember">{selectedCharacter?.name ?? "Персонаж"}</h2>
            <div className="mt-3 flex flex-col gap-3">
              <input className="field" placeholder="название" value={item.name} onChange={(event) => setItem({ ...item, name: event.target.value })} />
              <select className="field" value={item.rarity} onChange={(event) => setItem({ ...item, rarity: event.target.value })}>{rarities.map((rarity) => <option key={rarity}>{rarity}</option>)}</select>
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={item.is_consumable} onChange={(event) => setItem({ ...item, is_consumable: event.target.checked })} />Расходуемый</label>
              <button className="btn" onClick={() => action("item", item)}>Выдать предмет</button>
            </div>
          </div>
        </section>
        <section className="panel flex flex-col gap-3 p-5">
          <h2 className="text-lg font-semibold text-ember">Карма игроков</h2>
          <label className="field-label">
            <span>Игрок</span>
            <select className="field" value={karmaUserId} onChange={(event) => setKarmaUserId(event.target.value)}>
              {users.map((user) => <option value={user.id} key={user.id}>{user.username} · {user.karma} кармы</option>)}
            </select>
          </label>
          <label className="field-label">
            <span>Изменение кармы</span>
            <input className="field" type="number" value={karmaAmount} onChange={(event) => setKarmaAmount(Number(event.target.value))} />
          </label>
          <p className="text-sm text-white/65">{selectedUser?.username ?? "Игрок"}: {selectedUser?.karma ?? 0}</p>
          <button className="btn" onClick={applyKarma}>Применить</button>
        </section>
        {canManageRoles && (
          <section className="panel flex flex-col gap-3 p-5">
            <div className="flex items-center gap-2">
              <Shield size={18} className="text-ember" />
              <h2 className="text-lg font-semibold text-ember">Роли пользователей</h2>
            </div>
            <p className="text-sm text-white/55">
              {user?.is_owner
                ? "Назначайте роли. Доступно только владельцу и главному администратору."
                : "Главный администратор управляет ролями администраторов и игроков. Роль владельца недоступна."}
            </p>
            <div className="flex flex-col gap-2">
              {users.map((row) => (
                <div className="flex items-center justify-between gap-2 rounded-md bg-black/25 px-3 py-2" key={row.id}>
                  <span className="text-sm font-semibold text-ember">{row.username}</span>
                  <select
                    className="field max-w-[220px]"
                    value={row.role}
                    disabled={!canEditRole(row)}
                    onChange={(event) => changeRole(row.id, event.target.value as UserRole)}
                  >
                    {roleOptionsFor(row).map((role) => (
                      <option value={role} key={role}>{ROLE_LABELS[role]}</option>
                    ))}
                  </select>
                </div>
              ))}
            </div>
            {roleError && <p className="text-sm text-red-300">{roleError}</p>}
          </section>
        )}
      </div>
      <section className="panel p-5">
        <h2 className="text-lg font-semibold text-ember">Все персонажи</h2>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead className="text-xs uppercase text-white/45">
              <tr>
                <th className="py-2 pr-3">Имя</th>
                <th className="py-2 pr-3">Владелец</th>
                <th className="py-2 pr-3">Уровень</th>
                <th className="py-2 pr-3">Раса</th>
                <th className="py-2 pr-3">Подкласс</th>
                <th className="py-2 pr-3">Путь</th>
                <th className="py-2 pr-3"></th>
              </tr>
            </thead>
            <tbody>
              {characters.map((character) => (
                <tr className="border-t border-white/10" key={character.id}>
                  <td className="py-3 pr-3 font-semibold text-ember">{character.name}</td>
                  <td className="py-3 pr-3">{character.owner_username}</td>
                  <td className="py-3 pr-3">{character.level}</td>
                  <td className="py-3 pr-3">{character.race || "-"}</td>
                  <td className="py-3 pr-3">{character.subclass || "-"}</td>
                  <td className="py-3 pr-3">{character.route || "-"}</td>
                  <td className="py-3 pr-3"><Link className="btn-secondary" to={`/admin/characters/${character.id}`}>Открыть</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function AdminCharacterPage() {
  const { id: idParam } = useParams();
  const id = Number(idParam);
  const [character, setCharacter] = useState<Character | null>(null);
  const [form, setForm] = useState<Character | null>(null);
  const [inventory, setInventory] = useState<Inventory | null>(null);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [deleteConfirmation, setDeleteConfirmation] = useState("");
  const navigate = useNavigate();

  function load() {
    Promise.all([
      api.get<Character>(`/admin/characters/${id}`),
      api.get<Inventory>(`/admin/characters/${id}/inventory`)
    ]).then(([characterResponse, inventoryResponse]) => {
      setCharacter(characterResponse.data);
      setForm(characterResponse.data);
      setInventory(inventoryResponse.data);
    });
  }

  useEffect(load, [id]);

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!form) return;
    setError("");
    setSaved(false);

    const payload: Record<string, string | number | boolean | undefined> = {
      class_name: form.class_name
    };
    textFields.forEach(({ field }) => {
      payload[field] = form[field];
    });
    adminNumberFields.forEach(({ field }) => {
      payload[field] = form[field];
    });

    try {
      const response = await api.patch<Character>(`/admin/characters/${id}`, payload);
      setCharacter(response.data);
      setForm(response.data);
      setSaved(true);
    } catch (saveError) {
      setError(apiErrorDetail(saveError, "Не удалось сохранить персонажа"));
    }
  }

  async function deleteCharacter() {
    setError("");
    try {
      await api.delete(`/admin/characters/${id}`, {
        params: { confirmation: deleteConfirmation }
      });
      navigate("/admin");
    } catch (deleteError) {
      setError(apiErrorDetail(deleteError, "Не удалось удалить персонажа"));
    }
  }

  if (!character || !form) return <p>Загрузка...</p>;
  const stats = numberFields.filter((item) => !["level", "hp", "armor_class"].includes(item.field));

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
      <section className="panel p-5">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold text-ember">{character.name}</h1>
            <p className="text-white/70">{character.class_name} / {character.subclass || "-"} / {character.race || "-"}</p>
            <p className="text-sm text-white/55">Владелец: {character.owner_username}</p>
          </div>
          <Link className="btn-secondary" to="/admin">Назад</Link>
        </div>
        <form className="grid gap-3 md:grid-cols-2" onSubmit={save}>
          <div className="md:col-span-2">
            <ClassSelect value={form.class_name} onChange={(value) => {
              setSaved(false);
              setForm({ ...form, class_name: value });
            }} />
          </div>
          {textFields.map(({ field, label }) => (
            <label className="field-label" key={field}>
              <span>{label}</span>
              <input
                className="field"
                value={form[field]}
                onChange={(event) => {
                  setSaved(false);
                  setForm({ ...form, [field]: event.target.value });
                }}
              />
            </label>
          ))}
          {adminNumberFields.map(({ field, label }) => (
            <label className="field-label" key={field}>
              <span>{label}</span>
              <input
                className="field"
                type="number"
                value={form[field]}
                onChange={(event) => {
                  setSaved(false);
                  setForm({ ...form, [field]: Number(event.target.value) });
                }}
              />
            </label>
          ))}
          {error && <p className="text-sm text-red-300 md:col-span-2">{error}</p>}
          {saved && <p className="text-sm text-emerald-200 md:col-span-2">Сохранено</p>}
          <button className="btn md:col-span-2" type="submit"><Save size={16} />Сохранить изменения</button>
        </form>
        <dl className="mt-5 grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat label="Уровень" value={character.level} />
          <Stat label="XP" value={character.xp} />
          <Stat label="HP" value={character.hp} />
          <Stat label="КД" value={character.armor_class} />
          {stats.map((stat) => <Stat key={stat.field} label={stat.label} value={character[stat.field]} />)}
        </dl>
        <div className="mt-5 rounded-md border border-red-400/30 p-4">
          <h2 className="font-semibold text-red-200">Удаление персонажа</h2>
          <div className="mt-3 flex flex-wrap gap-2">
            <input className="field flex-1" placeholder="УДАЛИТЬ" value={deleteConfirmation} onChange={(event) => setDeleteConfirmation(event.target.value)} />
            <button className="btn-secondary border-red-400/40 text-red-100" disabled={deleteConfirmation !== "УДАЛИТЬ"} onClick={deleteCharacter}><Trash2 size={16} />Удалить персонажа</button>
          </div>
        </div>
      </section>
      <ReadOnlyInventoryPanel inventory={inventory} />
    </div>
  );
}

function ShopLogsPage() {
  const [logs, setLogs] = useState<ShopTransactionLog[]>([]);
  const [characters, setCharacters] = useState<Character[]>([]);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [filters, setFilters] = useState({ character_id: "", user_id: "", mode: "", date: "" });
  const [error, setError] = useState("");

  function loadLogs(nextFilters = filters) {
    const params = Object.fromEntries(
      Object.entries(nextFilters).filter(([, value]) => value)
    );
    setError("");
    api.get<ShopTransactionLog[]>("/admin/shop-logs", { params })
      .then((response) => setLogs(response.data))
      .catch((loadError) => setError(apiErrorDetail(loadError, "Не удалось загрузить логи")));
  }

  useEffect(() => {
    Promise.all([
      api.get<Character[]>("/admin/characters"),
      api.get<AdminUser[]>("/admin/users")
    ]).then(([characterResponse, userResponse]) => {
      setCharacters(characterResponse.data);
      setUsers(userResponse.data);
    });
  }, []);

  useEffect(() => {
    loadLogs();
  }, [filters]);

  function updateFilter(field: keyof typeof filters, value: string) {
    setFilters((current) => ({ ...current, [field]: value }));
  }

  function resetFilters() {
    setFilters({ character_id: "", user_id: "", mode: "", date: "" });
  }

  return (
    <section className="panel p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-ember">Логи магазина</h1>
          <p className="text-sm text-white/60">Покупки и продажи персонажей</p>
        </div>
        <Link className="btn-secondary" to="/admin">Назад</Link>
      </div>
      <div className="mt-5 grid gap-3 md:grid-cols-4">
        <label className="field-label">
          <span>Игрок</span>
          <select className="field" value={filters.user_id} onChange={(event) => updateFilter("user_id", event.target.value)}>
            <option value="">Все</option>
            {users.map((user) => <option key={user.id} value={user.id}>{user.username}</option>)}
          </select>
        </label>
        <label className="field-label">
          <span>Персонаж</span>
          <select className="field" value={filters.character_id} onChange={(event) => updateFilter("character_id", event.target.value)}>
            <option value="">Все</option>
            {characters.map((character) => <option key={character.id} value={character.id}>{character.name} · {character.owner_username}</option>)}
          </select>
        </label>
        <label className="field-label">
          <span>Операция</span>
          <select className="field" value={filters.mode} onChange={(event) => updateFilter("mode", event.target.value)}>
            <option value="">Все</option>
            <option value="buy">Покупка</option>
            <option value="sell">Продажа</option>
          </select>
        </label>
        <label className="field-label">
          <span>Дата</span>
          <input className="field" type="date" value={filters.date} onChange={(event) => updateFilter("date", event.target.value)} />
        </label>
      </div>
      <div className="mt-3 flex justify-end">
        <button className="btn-secondary" onClick={resetFilters}>Сбросить</button>
      </div>
      {error && <p className="mt-3 text-sm text-red-300">{error}</p>}
      <div className="mt-5 overflow-x-auto">
        <table className="w-full min-w-[860px] text-left text-sm">
          <thead className="text-xs uppercase text-white/45">
            <tr>
              <th className="py-2 pr-3">Дата</th>
              <th className="py-2 pr-3">Игрок</th>
              <th className="py-2 pr-3">Персонаж</th>
              <th className="py-2 pr-3">Операция</th>
              <th className="py-2 pr-3">Предмет</th>
              <th className="py-2 pr-3">Цена</th>
              <th className="py-2 pr-3">Наёмник</th>
              <th className="py-2 pr-3">Итого</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((log) => (
              <tr className="border-t border-white/10" key={log.id}>
                <td className="py-3 pr-3">{new Date(log.created_at).toLocaleString("ru-RU")}</td>
                <td className="py-3 pr-3">{log.username}</td>
                <td className="py-3 pr-3">{log.character_name}</td>
                <td className="py-3 pr-3">{log.mode === "buy" ? "Покупка" : "Продажа"}</td>
                <td className="py-3 pr-3">{log.item_name} · {log.rarity}</td>
                <td className="py-3 pr-3">{log.item_price} зм</td>
                <td className="py-3 pr-3">{log.hireling_cost} зм</td>
                <td className="py-3 pr-3 font-semibold text-ember">{log.total_amount} зм</td>
              </tr>
            ))}
            {logs.length === 0 && (
              <tr className="border-t border-white/10">
                <td className="py-6 text-center text-white/55" colSpan={8}>Записей нет</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function TransferLogsPage() {
  const [logs, setLogs] = useState<TransferLog[]>([]);
  const [characters, setCharacters] = useState<Character[]>([]);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [filters, setFilters] = useState({ character_id: "", user_id: "", transfer_type: "", date: "" });
  const [error, setError] = useState("");

  function loadLogs(nextFilters = filters) {
    const params = Object.fromEntries(
      Object.entries(nextFilters).filter(([, value]) => value)
    );
    setError("");
    api.get<TransferLog[]>("/admin/transfer-logs", { params })
      .then((response) => setLogs(response.data))
      .catch((loadError) => setError(apiErrorDetail(loadError, "Не удалось загрузить передачи")));
  }

  useEffect(() => {
    Promise.all([
      api.get<Character[]>("/admin/characters"),
      api.get<AdminUser[]>("/admin/users")
    ]).then(([characterResponse, userResponse]) => {
      setCharacters(characterResponse.data);
      setUsers(userResponse.data);
    });
  }, []);

  useEffect(() => {
    loadLogs();
  }, [filters]);

  function updateFilter(field: keyof typeof filters, value: string) {
    setFilters((current) => ({ ...current, [field]: value }));
  }

  function resetFilters() {
    setFilters({ character_id: "", user_id: "", transfer_type: "", date: "" });
  }

  return (
    <section className="panel p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-ember">Логи передач</h1>
          <p className="text-sm text-white/60">Валюта и предметы между персонажами</p>
        </div>
        <Link className="btn-secondary" to="/admin">Назад</Link>
      </div>
      <div className="mt-5 grid gap-3 md:grid-cols-4">
        <label className="field-label">
          <span>Игрок</span>
          <select className="field" value={filters.user_id} onChange={(event) => updateFilter("user_id", event.target.value)}>
            <option value="">Все</option>
            {users.map((user) => <option key={user.id} value={user.id}>{user.username}</option>)}
          </select>
        </label>
        <label className="field-label">
          <span>Персонаж</span>
          <select className="field" value={filters.character_id} onChange={(event) => updateFilter("character_id", event.target.value)}>
            <option value="">Все</option>
            {characters.map((character) => <option key={character.id} value={character.id}>{character.name} · {character.owner_username}</option>)}
          </select>
        </label>
        <label className="field-label">
          <span>Тип</span>
          <select className="field" value={filters.transfer_type} onChange={(event) => updateFilter("transfer_type", event.target.value)}>
            <option value="">Все</option>
            <option value="currency">Валюта</option>
            <option value="item">Предмет</option>
          </select>
        </label>
        <label className="field-label">
          <span>Дата</span>
          <input className="field" type="date" value={filters.date} onChange={(event) => updateFilter("date", event.target.value)} />
        </label>
      </div>
      <div className="mt-3 flex justify-end">
        <button className="btn-secondary" onClick={resetFilters}>Сбросить</button>
      </div>
      {error && <p className="mt-3 text-sm text-red-300">{error}</p>}
      <div className="mt-5 overflow-x-auto">
        <table className="w-full min-w-[920px] text-left text-sm">
          <thead className="text-xs uppercase text-white/45">
            <tr>
              <th className="py-2 pr-3">Дата</th>
              <th className="py-2 pr-3">Игрок</th>
              <th className="py-2 pr-3">Отправитель</th>
              <th className="py-2 pr-3">Получатель</th>
              <th className="py-2 pr-3">Тип</th>
              <th className="py-2 pr-3">Сумма</th>
              <th className="py-2 pr-3">Предмет</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((log) => (
              <tr className="border-t border-white/10" key={log.id}>
                <td className="py-3 pr-3">{new Date(log.created_at).toLocaleString("ru-RU")}</td>
                <td className="py-3 pr-3">{log.username}</td>
                <td className="py-3 pr-3">{log.sender_character_name}</td>
                <td className="py-3 pr-3">{log.recipient_character_name}</td>
                <td className="py-3 pr-3">{log.transfer_type === "currency" ? "Валюта" : "Предмет"}</td>
                <td className="py-3 pr-3">{log.gold} зм / {log.silver} см / {log.copper} мм</td>
                <td className="py-3 pr-3">{log.item_name ? `${log.item_name} · ${log.item_rarity}` : "-"}</td>
              </tr>
            ))}
            {logs.length === 0 && (
              <tr className="border-t border-white/10">
                <td className="py-6 text-center text-white/55" colSpan={7}>Записей нет</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ReadOnlyInventoryPanel({ inventory }: { inventory: Inventory | null }) {
  return (
    <aside className="panel p-5">
      <h2 className="text-lg font-semibold text-ember">Инвентарь</h2>
      <p className="mt-1 text-sm text-white/70">{inventory?.gold ?? 0} зм / {inventory?.silver ?? 0} см / {inventory?.copper ?? 0} мм</p>
      <div className="mt-4 rounded-md border border-white/10 p-3">
        <h3 className="font-semibold text-ember">Заметки</h3>
        <p className="mt-2 whitespace-pre-wrap text-sm text-white/75">{inventory?.notes || "Заметок нет"}</p>
      </div>
      <div className="mt-4 space-y-3">
        {inventory?.items.map((item) => (
          <div className="rounded-md border border-white/10 p-3" key={item.id}>
            <div className="font-semibold">{item.name}</div>
            <div className="text-sm text-white/60">{item.rarity} · {item.is_consumable ? "расходуемый" : "постоянный"}</div>
          </div>
        ))}
      </div>
    </aside>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return <div className="rounded-md bg-black/25 p-3"><dt className="text-xs uppercase text-white/45">{label}</dt><dd className="mt-1 text-lg font-semibold">{value}</dd></div>;
}

class ErrorBoundary extends Component<{ children: React.ReactNode }, { error: Error | null }> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <div className="grid min-h-screen place-items-center bg-[#101217] px-4 text-parchment">
          <div className="panel flex w-full max-w-sm flex-col gap-3 p-6">
            <h1 className="text-2xl font-bold text-ember">Что-то пошло не так</h1>
            <p className="text-sm text-white/70">Произошла ошибка. Попробуйте обновить страницу.</p>
            <button className="btn" onClick={() => window.location.reload()}>Обновить</button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/" element={<Protected><HomePage /></Protected>} />
        <Route path="/characters" element={<Protected><CharactersPage /></Protected>} />
        <Route path="/characters/new" element={<Protected><CharacterFormPage /></Protected>} />
        <Route path="/characters/:id" element={<Protected><CharacterPage /></Protected>} />
        <Route path="/characters/:id/edit" element={<Protected><CharacterFormPage edit /></Protected>} />
        <Route path="/shop" element={<Protected><ShopPage /></Protected>} />
        <Route path="/leaderboard" element={<Protected><LeaderboardPage /></Protected>} />
        <Route path="/chat" element={<Protected><ChatPage /></Protected>} />
        <Route path="/profile" element={<Protected><ProfilePage /></Protected>} />
        <Route path="/admin/shop-logs" element={<Protected><ShopLogsPage /></Protected>} />
        <Route path="/admin/transfer-logs" element={<Protected><TransferLogsPage /></Protected>} />
        <Route path="/admin/characters/:id" element={<Protected><AdminCharacterPage /></Protected>} />
        <Route path="/admin" element={<Protected><AdminPage /></Protected>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Router>
  );
}

createRoot(document.getElementById("root")!).render(<ErrorBoundary><App /></ErrorBoundary>);
