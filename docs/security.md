# Çalıştırma sınırı ve güvenlik modeli

KodArena kontrollü kodlarla, yerel veya ayrılmış bir geliştirme VM'inde kullanılan laboratuvardır. Genel internete açılacak bir kod çalıştırma hizmetinin güvenlik onayına sahip değildir.

## Uygulanan sınırlar

- API ve worker anahtarları farklıdır. Kullanıcı anahtarı worker uçlarına, worker anahtarı kullanıcı uçlarına erişemez.
- API Docker çağrısı yapmaz. Worker konteynere credential, veritabanı, host dizini veya Docker soketi bağlamaz.
- Docker çağrıları argüman listesiyle, shell açmadan yapılır. Runtime ve komut şablonu sunucu tarafından belirlenir.
- Test konteyneri UID 65534 ile, ağsız, salt okunur root filesystem ve düşürülmüş Linux capability'leriyle başlar.
- Varsayılan Docker seccomp profili korunur; no-new-privileges etkin.
- Bellek ve swap toplamı 128 MB, CPU kotası 0,5, süreç sınırı 32; dosya descriptor ve CPU ulimit değerleri sınırlı.
- Yazılabilir /tmp en fazla 16 MB, noexec ve nosuid seçeneklidir.
- Docker log driver kapalıdır; uygulama çıktısı sınırlandırılarak okunur.
- Worker 2 saniyelik duvar süresi uygular; cleanup aşamasında konteyneri zorla kaldırır.
- Konteyner içindeki 5 saniyelik timeout ve CPU ulimit, worker aniden kapandığında sıradan hatalı kod için ek durdurma katmanıdır.

## Güven sınırları

Worker güvenilir bileşendir ve Docker Engine erişimi güçlü bir yetkidir. Worker anahtarı test tanımlarını görmeye ve sonuç bildirmeye izin verir; bu anahtar son kullanıcıya verilmez.

Konteyner içindeki timeout düşmanca koda karşı bağımsız güvenlik duvarı değildir. Aynı UID ile çalışan süreçler birbirlerine sinyal gönderebilir; container escape açıkları ve host kernel kaynakları da kapsamlı bir tehdit modeline dahildir. Worker veya Docker çökerse konteyner temizliği garanti edilemez. Operatör kalan kodarena.managed=true etiketli konteynerleri kontrol etmelidir.

Genel erişime açmadan önce ayrı ve geçici worker VM'leri / daha güçlü sandbox, bağımsız container reaper, ağ ve disk kotaları, kimlik yönetimi, rate limiting, TLS, image digest sabitleme ve saldırı testleri gerekir. Bunlar mevcut sürümde tamamlanmış özellikler değildir.

## Kaynaklar

- [Docker Engine security](https://docs.docker.com/engine/security/)
- [Docker run seçenekleri](https://docs.docker.com/reference/cli/docker/container/run/)
- [Rootless mode](https://docs.docker.com/engine/security/rootless/)

Rootless Docker riski azaltabilir; limit desteği host ve cgroup ayarlarına bağlı olduğundan kurulumda ayrıca doğrulanmalıdır.
