# Tek komutla Linux kurulumu

TradingAgents'ı bir Linux sunucusunda **tek komutla** kurup `systemd` servisi olarak çalıştırır.

```bash
sudo bash deploy/install.sh
```

Bittiğinde tarayıcıdan `http://SUNUCU_IP:8000` adresine gidip, script'in ekrana yazdığı
admin kullanıcı adı/şifresiyle giriş yaparsınız.

---

## Ne yapar?

1. **Sistem paketleri** — Python 3.10+, Node 20 (Vite için), PostgreSQL, git, curl
2. **Python sanal ortamı** (`.venv`) + `backend/requirements.txt`
   *(pip `tradingagents` paketine gerek yok — yerel `backend/trading_agents` kullanılır)*
3. **Frontend build** (`npm run build`) → `frontend/dist` (backend tarafından sunulur, ayrı sunucu gerekmez)
4. **PostgreSQL** veritabanı + kullanıcı (rastgele şifreyle)
5. **`.env`** — güvenli rastgele `SECRET_KEY`, `ENCRYPTION_KEY`, DB şifresi ve admin şifresi üretir
   *(yalnızca `.env` yoksa — mevcut dosyayı asla ezmez)*
6. **systemd servisi** — açılışta otomatik başlar, çökünce yeniden başlar
7. Servisi başlatır, **sağlık kontrolü** yapar, erişim bilgilerini yazdırır

Tamamen **idempotent**: tekrar çalıştırmak güvenlidir (kod güncelledikten sonra yeniden çalıştırıp `systemctl restart` yapabilirsiniz).

## Gereksinimler

- Debian/Ubuntu (`apt`) veya Fedora/RHEL/Rocky/Alma (`dnf`/`yum`)
- `systemd` ve `root` (sudo) yetkisi

## Özelleştirme (opsiyonel ortam değişkenleri)

```bash
sudo APP_PORT=80 ADMIN_USERNAME=patron bash deploy/install.sh
```

| Değişken | Varsayılan | Açıklama |
|---|---|---|
| `APP_PORT` | `8000` | Dinlenecek port (80 de olur — servis `CAP_NET_BIND_SERVICE` ile gelir) |
| `SERVICE_NAME` | `tradingagents` | systemd servis adı |
| `SERVICE_USER` | sudo'yu çağıran kişi | Servisi çalıştıracak kullanıcı |
| `ADMIN_USERNAME` | `admin` | Panel admin kullanıcı adı |
| `ADMIN_PASSWORD` | rastgele | Belirtmezseniz güvenli rastgele üretir ve ekrana yazar |
| `NODE_MAJOR` | `20` | Kurulacak Node sürümü |
| `SKIP_DB` | `0` | `1` → harici PostgreSQL kullan (DB kurulumunu atla) |
| `BUILD_FRONTEND` | `1` | `0` → yalnızca API (UI derleme atlanır) |

## Kurulumdan sonra: LLM anahtarı ekleyin

Analiz çalışması için en az bir LLM sağlayıcı anahtarı gerekir:

```bash
sudo nano .env                       # OPENAI_API_KEY / ANTHROPIC_API_KEY / ...
sudo systemctl restart tradingagents
```

## Otomatik güncelleme (uygulama içi "Güncelle" butonu)

Kurulum, uygulamaya **kendi kendini güncelleme** yeteneği ekler:

- Backend periyodik olarak git remote'unu kontrol eder (`origin/main`).
- Yeni commit geldiğinde **tüm giriş yapmış kullanıcılar** arayüzün üstünde bir
  bildirim çubuğu görür ("Yeni sürüm mevcut — **Güncelle**").
- **Güncelle**'ye tıklayınca: `git pull` → `pip install` → frontend build →
  servisi yeniden başlatır. Sayfa, güncelleme bitince otomatik yenilenir.

**Nasıl çalışır (güvenlik):** Güncelleme ayrı bir `tradingagents-update.service`
(oneshot) içinde çalışır; ana servisi yeniden başlatmak bu süreci öldürmez.
Backend kullanıcısı yalnızca **bu tek servisi başlatma** yetkisine sahiptir
(`/etc/sudoers.d/...` ile, başka hiçbir komut değil). `git pull` ve build adımları
ayrıcalıksız `RUN_USER` olarak çalışır; yalnızca servis restart'ı root'tur — yani
çekilen kod root yetkisi kazanmaz.

> Gereksinim: checkout `RUN_USER`'a ait olmalı (kurulum bunu otomatik yapar) ve
> repo **public** olmalı ya da `RUN_USER` için git kimlik bilgisi tanımlı olmalı.

Manuel güncelleme (UI olmadan): `sudo bash deploy/update.sh`

## Yönetim

```bash
journalctl -u tradingagents -f          # canlı log
systemctl status tradingagents
systemctl restart tradingagents
systemctl stop tradingagents
```

## Kaldırma

```bash
sudo bash deploy/uninstall.sh           # servisi kaldırır (DB ve .env korunur)
sudo bash deploy/uninstall.sh --purge   # + veritabanını, .env ve venv'i siler
```

## Notlar

- **Tek process zorunlu.** Servis `uvicorn`'u tek process çalıştırır. Uygulama
  in-memory WebSocket yöneticisi ve in-process APScheduler cron kullanır; birden çok
  worker bunları çoğaltır (çift analiz / bozuk WebSocket). Unit'e `--workers` **eklemeyin**.
- **Özel servis kullanıcısı** (`SERVICE_USER`) kullanacaksanız projeyi `/root` altına değil
  `/opt` veya `/srv` gibi bir dizine koyun (izin/erişim için).
- Frontend, backend tarafından `frontend/dist`'ten sunulur — ayrı bir web sunucusu (nginx) gerekmez.
  TLS/alan adı isterseniz önüne nginx/Caddy reverse proxy koyabilirsiniz.
