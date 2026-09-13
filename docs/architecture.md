# Mimari kararlar

## İşin yaşam döngüsü

~~~mermaid
stateDiagram-v2
    [*] --> queued: Gönderim
    queued --> running: Atomik claim
    running --> queued: Lease kaybı / altyapı hatası
    running --> accepted: Tüm testler başarılı
    running --> rejected: Test hatası
    running --> system_error: 3 deneme doldu
    queued --> cancelled: Kullanıcı iptali
    running --> cancelled: Kullanıcı iptali
~~~

Şemadaki rejected; wrong_answer, time_limit, memory_limit, output_limit ve runtime_error durumlarını topluca gösterir. Bunlar yeniden denenmez; kodun değerlendirme sonucudur. Altyapı hataları 2 ve 4 saniyelik beklemeyle yeniden kuyruğa girer. Üçüncü başarısız deneme system_error ile sonlanır.

## Claim ve fencing

İş alma BEGIN IMMEDIATE işlemi içinde yapılır. Süresi dolan işler kurtarılır, sıradaki uygun iş seçilir ve rastgele bir lease token atanır. İki worker aynı satırı eşzamanlı sahiplenemez. Aynı worker kimliği aynı anda tek iş alabilir.

Her heartbeat ve sonuç için iş kimliği, worker kimliği, lease token, durum ve son kullanma zamanı birlikte kontrol edilir. İlk worker donup daha sonra geri dönerse eski token ile sonuç yazamaz. Sonuç kaydı ve olay kaydı aynı transaction içindedir.

Worker her 3 saniyede bir heartbeat gönderir; HTTP çağrısı en fazla 5 saniye bekler. İptal veya koordinatör hatasında devam eden konteyner durdurulur. İptal veritabanında anında görünür; konteynerin durması heartbeat aralığı, HTTP timeout ve Docker temizleme süresi kadar gecikebilir.

Recovery yeni claim geldiğinde çalışır. Hiç worker yoksa süre dolmuş iş ekranda running kalabilir; çalışan bir worker yeniden claim yaptığında düzeltilir. Bu davranış ayrı bir scheduler gereksinimini ortadan kaldırır.

## Idempotency ve yük kontrolü

İstemci her yeni gönderime bir Idempotency-Key üretir. Veritabanında anahtar tekildir; içerik özetiyle birlikte kontrol edilir. Aynı anahtar + aynı içerik mevcut işi döndürür, farklı içerik 409 üretir. Tarayıcı ağ hatasında aynı isteği yeniden denerken anahtarı korur.

Aktif kuyruk kapasitesi 100'dür. Kuyruk doluyken yeni işler 429 alır; mevcut isteğin tekrarı sonuç kimliğini almaya devam eder. Kaynak en fazla 16.000 UTF-8 bayt; istek gövdesi en fazla 96.000 bayttır. Tamamlanan işler için otomatik saklama süresi yoktur; uzun süreli kullanımda arşivleme eklenmelidir.

## Değerlendirme

Problem tanımı, testler, sürüm ve limitler gönderim anında kopyalanır. Problem daha sonra değişse bile sıradaki işin tanımı değişmez. Beklenen çıktı worker'da karşılaştırılır, test konteynerine gönderilmez.

Her test taze bir konteynerde çalışır. Satır sonundaki boşluklar ve çıktının sonundaki boş satırlar yok sayılır; satır içindeki boşluklar ve baştaki boşluklar korunur. Tüm testler çalışır; genel sonuç ilk başarısız testin verdict değeridir.

Çıktı okuma ayrı thread'lerde yapılır. stdout ve stderr için ortak 16 KiB bütçe vardır. Karşılaştırma bu bütçe içindeki tam çıktı üzerinde yapılır; gösterim için en fazla 4096 karakter tutulur. Gizli test stdout/stderr değerleri API'de kalıcı kayıttan önce silinir.

## SQLite tercihi

WAL ve kısa yazma işlemleri, bir API'ye bağlanan az sayıda yerel worker için yeterli bir başlangıç sağlar. Veritabanı gerçek dosyadır; kuyruk testlerinde mock kullanılmaz. Ağ paylaşımına SQLite dosyası koymak veya çok makineli yüksek ölçek iddiasında bulunmak bu tasarımın kapsamı değildir.

Büyütme yönü PostgreSQL'e geçiş, satır kilidiyle claim, saklama politikası ve kullanıcı bazlı kota olur. Sadece teknoloji sayısını artırmak için ek mesaj sunucusu kullanılmadı.

## Panel güncellemeleri

Olaylar monoton seq numarasıyla saklanır. Panel iki saniyede bir son gördüğü numaradan devam eder, böylece bağlantı kesintisinden sonra olayları yeniden okuyabilir. WebSocket veya SSE kullanılmaz. İş listesi ilk queued olayının numarasıyla sayfalanır; yeni gönderimler eski sayfanın sınırını kaydırmaz.
