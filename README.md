# KodArena

Python ve JavaScript çözümlerini test eden, iş kuyruğu ve ayrı çalıştırıcıları olan bir kod değerlendirme uygulaması.

KodArena'da odak noktam, bir çözümün doğru çıktı üretmesi kadar arka plandaki işin güvenilir biçimde tamamlanması. Worker kapanırsa iş yeniden sıraya giriyor; eski worker'ın geç gelen sonucu kabul edilmiyor. Aynı isteğin tekrar gönderilmesi ikinci bir iş oluşturmuyor.

**Kapsam:** Tek kullanıcıya ait yerel bir çalışma alanı ve kontrollü kodlarla kullanılan bir mühendislik laboratuvarı. İnternete açık, güvenilmeyen kullanıcıların kodunu çalıştıran bir servis olarak tasarlanmadı.

## Neler var?

- Python 3.12 ve JavaScript / Node.js 22 desteği.
- Üç sürümlü problem: iki sayı toplamı, dengeli parantezler ve aralık birleştirme.
- Kod editörü, problem örnekleri, kuyruk görünümü, test sonuçları ve olay geçmişi.
- Her test için ayrı Docker konteyneri; kapalı ağ, salt okunur kök dosya sistemi, root olmayan kullanıcı.
- Test başına 128 MB bellek, 0,5 CPU, 32 süreç ve toplam 16 KiB çıktı sınırı.
- Worker tarafında 2 saniyelik duvar süresi; ayrı stdout / stderr toplama.
- Süreli iş sahipliği, heartbeat, yeniden deneme, iptal ve deneme sınırı.
- İstek anahtarıyla tekrar gönderim kontrolü; problem ve testlerin gönderim anında sürümlü kopyası.
- Gizli testlerin girdisi, beklenen çıktısı ve program çıktısı kullanıcı API'sine verilmez.
- OpenAPI, otomatik testler ve gerçek Docker testlerini içeren CI yapılandırması.

## Mimari

~~~mermaid
flowchart LR
    UI[Tarayıcı] -->|Kullanıcı anahtarı| API[FastAPI]
    API --> DB[(SQLite WAL\nİşler ve olaylar)]
    W1[Worker 1] -->|Worker anahtarı\nClaim / heartbeat / sonuç| API
    W2[Worker 2] --> API
    W1 --> D[Docker Engine]
    W2 --> D
    D --> P[Python test konteyneri]
    D --> J[JavaScript test konteyneri]
~~~

API Docker soketine erişmez. Worker işleri HTTP üzerinden alır; veritabanına doğrudan bağlanmaz. Yerel kurulumda ek bir mesaj sunucusuna ihtiyaç duymamak için kuyruk SQLite işlemleriyle tutulur. Bu, çok makineye yayılan yüksek trafikli bir kuyruk iddiası değildir.

## Kurulum

Gerekenler: Python 3.12, Docker Desktop veya Linux Docker Engine. Windows'ta Docker'ın **Linux containers** modunda çalışması gerekir.

Repo klasöründe:

~~~powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe scripts/setup.py
docker pull python:3.12-slim
docker pull node:22-slim
~~~

Birinci terminalde API:

~~~powershell
.\.venv\Scripts\python.exe scripts/start.py api
~~~

İkinci terminalde worker:

~~~powershell
.\.venv\Scripts\python.exe scripts/start.py worker --id worker-1
~~~

İkinci bir worker denemek için yeni terminalde aynı komutu farklı bir kimlikle çalıştır:

~~~powershell
.\.venv\Scripts\python.exe scripts/start.py worker --id worker-2
~~~

Linux / macOS'ta aynı komutlarda Python yolu olarak .venv/bin/python kullanılır.

Panel: [localhost:5200](http://localhost:5200) · API belgeleri: [localhost:5200/docs](http://localhost:5200/docs).

.env dosyasındaki ARENA_API_KEY değerini panelin bağlantı alanına gir. Anahtar tarayıcı depolamasına yazılmaz; sekme yenilenince yeniden giriş gerekir. Worker anahtarını panelde kullanma.

Docker kapalıysa API ve editör açılır, gönderimler kuyrukta bekler. Worker başlangıç kontrolünde durur; kod bilgisayarda doğrudan çalıştırılmaz.

### API'yi Docker ile çalıştırma

Yerelde çalışan API'yi durdurduktan sonra:

~~~powershell
docker compose up --build -d
.\.venv\Scripts\python.exe scripts/start.py worker --id worker-1
~~~

Compose yalnızca API'yi başlatır; worker host üzerinde ayrı süreçtir. Böylece API konteynerine Docker soketi bağlanmaz. API verisi arena-data volume'unda kalır; yerel API'nin data/arena.db dosyasından ayrıdır.

## Denenecek senaryolar

1. İki sayı toplamı probleminin başlangıç kodunu gönder: tüm testler başarılı olmalı.
2. Aynı problemde yalnızca print(0) gönder: yanlış cevap beklenir.
3. Python'da sonsuz döngü gönder: süre sınırı beklenir.
4. Kuyruktaki bir işi iptal et: worker bu işi almamalı.
5. Worker'ı bir iş devam ederken kapat; başka worker açık kalsın: 30 saniyelik lease dolunca iş yeniden alınır. En fazla üç deneme yapılır.

İş **en az bir kez** çalıştırılabilir. Geçersiz lease ile gelen sonuç kabul edilmediği için yalnızca güncel denemenin sonucu kaydedilir. Bu, kodun tam olarak bir kez çalışacağı anlamına gelmez.

## Testler

~~~powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check arena scripts tests
~~~

Gerçek Docker testleri ayrıca açılır:

~~~powershell
$env:ARENA_DOCKER_TESTS = "1"
.\.venv\Scripts\python.exe -m pytest tests/test_docker.py -q
~~~

API ve worker çalışırken uçtan uca kontrol:

~~~powershell
.\.venv\Scripts\python.exe scripts/smoke.py
~~~

Yerel sonuçlar ve çalıştırılmamış kontroller [doğrulama notlarında](docs/validation.md).

## Bilinen sınırlar

- Oturumlar tek çalışma alanını paylaşır; ayrı kullanıcı hesapları veya çok kiracılı veri izolasyonu yok.
- Python ve JavaScript yorumlanır. Sözdizimi hataları çalıştırma hatası olarak raporlanır; C++ derleme desteği yok.
- Ölçülen süre Docker başlatma / bağlantı maliyetini de içerir; algoritmanın saf CPU süresi değildir.
- Bellek sınırı etiketi Docker'ın OOMKilled bilgisinden gelir. Dilin kendi MemoryError hatası veya Node heap hatası çalıştırma hatası olabilir. En yüksek bellek kullanımı ölçülmez.
- Kaynak kodu veritabanında saklanır. Koda anahtar veya kişisel veri koyulmamalı.
- Gizli testler kullanıcı API'sinden saklanır; bu açık kaynak repodaki alıştırmalar bir sınav gizliliği sağlamaz.
- Varsayılan runtime image etiketleri güncellenebilir. Tekrarlanabilir çalıştırmalar için image digest'leri sabitlenebilir.
- Konteynerler host kernel'ini paylaşır. Docker sınırları tek başına düşmanca kodu güvenle barındırma garantisi değildir.

Kararların ayrıntıları: [mimari](docs/architecture.md), [güvenlik modeli](docs/security.md), [öğrenme ve demo rehberi](docs/learning-guide.md).
