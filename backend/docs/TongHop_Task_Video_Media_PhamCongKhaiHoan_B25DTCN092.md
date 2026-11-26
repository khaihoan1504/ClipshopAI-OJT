# TỔNG HỢP KIẾN THỨC & TÀI LIỆU KỸ THUẬT PHÂN HỆ VIDEO, FEED, SẢN PHẨM GẮN KÈM & CLOUDFLARE R2

- **Người phụ trách:** Phạm Công Khải Hoàn (`B25DTCN092`)
- **Dự án:** ClipShop AI — Nền tảng video ngắn kết hợp thương mại điện tử và trợ lý AI

---

## TÓM TẮT NHANH (ĐỌC GỌN TRÊN ĐIỆN THOẠI)

- **CSDL phụ trách:**
  - **2 bảng chính:** `videos` (lưu video, thumbnail, thời lượng, lượt xem, `VISIBLE/HIDDEN`, kiểm duyệt) và `video_products` (bảng trung gian nối N–N giữa video và sản phẩm, tối đa 3 sản phẩm/video, `ON DELETE CASCADE`).
  - **8 bảng liên quan:** `users`, `shops`, `products`, `product_images`, `categories`, `likes`, `comments`, `follows`.
- **7 task đã làm & luồng cốt lõi:**
  1. **API Đăng video:** Kiểm tra định dạng/thời lượng ≤ 60s, dung lượng ≤ 50MB. Trên Vercel dùng **Direct-to-R2** (`upload-urls` → trình duyệt `PUT` thẳng lên R2 để né giới hạn 4.5MB của Vercel → `direct` kiểm tra `head_object` + lưu DB, lỗi thì rollback cả DB lẫn R2).
  2. **API Feed & Video 1 người:** `GET /api/videos/feed` lọc `VISIBLE` dùng **Cursor Pagination** (`id < cursor`) để cuộn mượt không trùng; `GET /api/videos/users/{user_id}` hỗ trợ `include_hidden=true` cho chủ sở hữu/Admin; `POST /api/videos/{id}/views` tăng lượt xem.
  3. **UI Feed cuộn dọc:** `scroll-snap-type: y mandatory` hít từng video, `IntersectionObserver` tự phát video đang hiện ≥ 75% và tính 1 view sau 3s, mobile gọn navbar 1 dòng + full `100dvh`.
  4. **UI Trang đăng video:** Đọc thời lượng video trên trình duyệt bằng `<video>`, tự cắt khung hình bằng `<canvas>` làm thumbnail, chọn tối đa 3 sản phẩm, có thanh `%` tiến trình.
  5. **Hồ sơ & Quản lý video:** Xem lưới video trên hồ sơ (`profile.html`), sửa mô tả (`PATCH`) và xóa video (`DELETE` — xóa cả DB lẫn file trên R2) tại `my-videos.html`.
  6. **Gắn sản phẩm vào video:** `POST /api/videos/{id}/products` kiểm tra quyền chủ video, chỉ cho gắn tối đa 3 sản phẩm `ACTIVE` của chính Shop mình.
  7. **Cloudflare R2:** Tách driver `LocalStorage` / `R2Storage` (`boto3` S3 API), và dùng `resolve_media_url()` tạo **Presigned GET URL** (hạn 3600s) để xem video/ảnh ổn định, an toàn.

---

## PHẦN 1. CÁC BẢNG CƠ SỞ DỮ LIỆU (CSDL) LIÊN QUAN

Trong toàn bộ các task bạn phụ trách, dữ liệu được lưu ở **2 bảng chính** (`videos`, `video_products`) và kết nối với **8 bảng liên quan** khác trong hệ thống:

### 1.1. Hai bảng chính của phân hệ Video

#### 1) Bảng `videos` — Lưu thông tin từng video ngắn
Defined in: `backend/app/models/video.py`

| Cột | Kiểu dữ liệu | Ý nghĩa dễ hiểu |
|---|---|---|
| `id` | `BIGINT` (PK, tự tăng) | Mã định danh duy nhất của mỗi video (`1, 2, 3...`). |
| `user_id` | `BIGINT` (FK → `users.id`, có index) | ID của người đã đăng video này. |
| `title` | `VARCHAR(255)` | Tiêu đề video (bắt buộc nhập). |
| `description` | `TEXT` (nullable) | Mô tả video (có thể chứa hashtag `#xuhuong`, `#review`...). |
| `hashtags` | `JSON` (nullable) | Mảng các hashtag tách ra từ mô tả để tìm kiếm & thống kê xu hướng. |
| `video_url` | `VARCHAR(500)` | Đường dẫn lưu file video (trên local là `/uploads/videos/...`, trên R2 là URL R2 của object `videos/...`). |
| `thumbnail_url` | `VARCHAR(500)` (nullable) | Đường dẫn ảnh bìa (thumbnail) của video (`covers/...`). |
| `duration_seconds` | `INTEGER` | Thời lượng video tính bằng giây. Có ràng buộc `CheckConstraint("duration_seconds > 0")` (chỉ lưu khi > 0 giây, tối đa 60 giây ở tầng kiểm tra). |
| `view_count` | `BIGINT` (mặc định `0`) | Tổng số lượt xem video. |
| `status` | `ENUM('VISIBLE', 'HIDDEN')` | Trạng thái hiển thị: `VISIBLE` (đang hiện công khai), `HIDDEN` (bị ẩn bởi chủ video hoặc Admin kiểm duyệt). |
| `created_at` | `DATETIME` | Thời điểm đăng video (lưu giờ UTC trên DB). |
| `moderation_reason` | `VARCHAR(500)` (nullable) | Lý do nếu bị Admin ẩn video vi phạm. |
| `moderated_by` | `BIGINT` (FK → `users.id`, nullable) | ID Admin đã ẩn video. |
| `moderated_at` | `DATETIME` (nullable) | Thời điểm Admin ẩn video. |

> **Index quan trọng:** `ix_videos_status_created_at (status, created_at)` giúp lọc các video `VISIBLE` mới nhất cực nhanh khi người dùng lướt Feed.

---

#### 2) Bảng `video_products` — Bảng trung gian gắn Sản phẩm vào Video (Quan hệ Nhiều–Nhiều)
Defined in: `backend/app/models/video.py`

Vì **1 video** có thể gắn tối đa **3 sản phẩm**, và **1 sản phẩm** có thể xuất hiện trong **nhiều video** khác nhau, ta không thể lưu trực tiếp `product_id` trong bảng `videos`, mà phải tách ra bảng trung gian `video_products`:

| Cột | Kiểu dữ liệu | Ý nghĩa dễ hiểu |
|---|---|---|
| `video_id` | `BIGINT` (PK, FK → `videos.id`, `ON DELETE CASCADE`) | ID của video. Khi video bị xóa, các dòng gắn kết trong `video_products` cũng tự động xóa theo (`CASCADE`). |
| `product_id` | `BIGINT` (PK, FK → `products.id`, có index) | ID của sản phẩm được gắn vào video. |

- Cặp `(video_id, product_id)` cùng làm **khóa chính kép (Composite Primary Key)** nên 1 sản phẩm không bao giờ bị gắn trùng 2 lần vào cùng 1 video.

---

### 1.2. Các bảng liên quan khác (kết nối sang phân hệ của thành viên khác)

| Bảng | Liên kết với phân hệ Video như thế nào? |
|---|---|
| `users` | Lấy thông tin người đăng video (`username`, `display_name`, `avatar_key`) để hiện trên Feed, Hồ sơ, và kiểm tra quyền chủ sở hữu khi sửa/xóa video. |
| `shops` | Kiểm tra xem người đăng video có phải chủ cửa hàng (`owner_id == user.id`) hay không trước khi cho phép gắn sản phẩm vào video. |
| `products` | Lấy tên, giá, tồn kho, trạng thái (`ACTIVE`) của các sản phẩm gắn trong video (`video_products`). |
| `product_images` | Lấy ảnh đại diện (`is_primary = true`, `object_key`) của sản phẩm để hiện thẻ giỏ hàng trong video trên Feed. |
| `categories` | Lấy tên danh mục khi trả về chi tiết sản phẩm gắn trong video (`serialize_product_item`). |
| `likes` | Đếm tổng lượt thích và kiểm tra người xem hiện tại đã tim video chưa. |
| `comments` | Hiển thị số lượng và danh sách bình luận (kèm trả lời lồng nhau như TikTok) của từng video. |
| `follows` | Dùng để kiểm tra nút Theo dõi người đăng ngay trên video và phục vụ tab "Đang theo dõi". |

---

## PHẦN 2. GIẢI THÍCH CHI TIẾT LOGIC TỪNG TASK

### Task 1: API Đăng video (`backend/app/routers/videos.py`)

Có **2 cách đăng video** chạy song song tùy theo môi trường lưu trữ (`local` hay `r2`):

1. **Cách truyền thống (Local / File nhỏ):** `POST /api/videos`
   - Nhận `multipart/form-data` gồm: `title`, `video` (file), `thumbnail` (file), `description`, `product_ids`.
   - Lưu tạm vào thư mục `TemporaryDirectory()`, gọi `prepare_video_upload()` & `prepare_thumbnail_upload()` kiểm tra định dạng (MP4/WebM, JPG/PNG/WebP), dung lượng (tối đa 50MB), và dùng `ffprobe` đo thời lượng (≤ 60 giây).
   - Gọi `save_uploaded_video()` đẩy file lên R2 (hoặc ổ đĩa local), rồi ghi vào bảng `videos` và `video_products`.
   - Nếu có lỗi ở bất kỳ bước nào → `db.rollback()` và xóa file đã tải lên để không có rác.

2. **Cách tải thẳng lên R2 (Direct-to-R2 — bắt buộc khi chạy trên Vercel):**
   - **Vì sao cần cách này?** Vercel Serverless giới hạn cứng mỗi request gửi qua backend chỉ được tối đa **4.5 MB**. Nếu gửi video 10–50 MB qua `/api/videos`, Vercel sẽ chặn ngay bằng lỗi `413 Payload Too Large` trước khi kịp vào code FastAPI.
   - **Luồng chạy 3 bước kèm Checkpoint an toàn:**
     - **Bước 1 (`POST /api/videos/upload-urls`):** Frontend gửi *tên file, kiểu file, dung lượng* (chỉ vài trăm byte JSON). Backend kiểm tra dung lượng (video ≤ 50MB, ảnh ≤ 5MB), rồi dùng `boto3` tạo ra **2 đường link ký sẵn (Presigned PUT URL)** có hạn 15 phút để trình duyệt tự đẩy file thẳng lên R2.
     - **Bước 2 (Trình duyệt → R2):** Trình duyệt dùng `axios.put(...)` đẩy thẳng file ảnh bìa (`covers/...`) và file video (`videos/...`) lên Cloudflare R2. Lúc này dữ liệu **không đi qua Vercel**, nên upload được tới **50 MB**. Trong lúc này DB chưa ghi gì cả (nếu rớt mạng thì Feed không bị rác).
     - **Bước 3 (`POST /api/videos/direct` — Checkpoint & Rollback):**
       - **Checkpoint 1 (`head_object`):** Backend hỏi thẳng R2 xem 2 file `video_key` và `thumbnail_key` đã thực sự nằm trên R2 chưa. Nếu thiếu 1 trong 2 → xóa file còn lại và báo lỗi `400`.
       - **Checkpoint 2 (Transaction DB nguyên tử):** Ghi dòng mới vào bảng `videos` và gắn `product_ids` vào `video_products` trong **cùng 1 transaction**, rồi mới `db.commit()`. Nếu có lỗi khi lưu DB hoặc gắn sản phẩm → `db.rollback()` **và xóa luôn 2 file trên R2**.

---

### Task 2: API Feed "Dành cho bạn" & Video của 1 người dùng (`backend/app/routers/videos.py`, `backend/app/crud/video.py`)

1. **Feed Dành cho bạn — `GET /api/videos/feed?limit=10&cursor=...`**
   - Chỉ lấy video có `status == 'VISIBLE'`.
   - **Dùng Cursor Pagination thay vì Page/Offset (`skip/limit`):**
     - Thay vì hỏi "lấy trang 2 bỏ qua 10 dòng đầu" (dễ bị lặp hoặc sót video khi có người mới đăng video trong lúc bạn đang lướt), ta truyền `cursor` là **ID của video cuối cùng** ở lần tải trước.
     - Backend truy vấn các video có `id < cursor` (sắp xếp mới nhất trước), lấy `limit + 1` dòng: nếu có đủ `limit + 1` thì biết chắc còn trang sau (`has_more = True`) và trả về `next_cursor = items[-1].id`.
   - Mỗi video trả về được gắn kèm danh sách sản phẩm (`products`) từ `video_products` và ảnh/video đã qua `resolve_media_url()`.

2. **Video của 1 người dùng — `GET /api/videos/users/{user_id}?include_hidden=false`**
   - Lọc theo `Video.user_id == user_id`.
   - Nếu `include_hidden=True`, backend kiểm tra `user` đang đăng nhập **phải là chủ sở hữu (`user.id == user_id`) hoặc `ADMIN`** (`allow_hidden`). Người lạ gọi `include_hidden=True` vẫn chỉ thấy video `VISIBLE`.

3. **Ghi nhận lượt xem — `POST /api/videos/{video_id}/views`**
   - Tăng `view_count = view_count + 1` trực tiếp trong DB khi người dùng xem video quá 3 giây.

---

### Task 3: UI Feed Video Cuộn Dọc (`frontend/pages/feed.html`, `frontend/js/pages/feed.js`, `frontend/css/style.css`)

- **Cuộn từng video dứt khoát như TikTok:**
  - Khung `.feed-container` dùng CSS `scroll-snap-type: y mandatory;` và mỗi slide video (`.feed-video-card`) dùng `scroll-snap-align: start; scroll-snap-stop: always;`. Khi vuốt nhẹ, trình duyệt tự hít vào đúng 1 video trọn khung hình.
- **Tự động phát & tạm dừng thông minh (`IntersectionObserver`):**
  - Theo dõi tỷ lệ hiển thị của từng `<video>` trong khung nhìn (`threshold: 0.75`). Video nào chiếm ≥ 75% màn hình sẽ tự `play()`, các video còn lại tự `pause()`.
  - Khi video đang phát được **3 giây**, frontend mới gọi `POST /api/videos/{id}/views` (và chỉ gọi 1 lần cho mỗi video trong phiên xem).
- **Tải thêm vô tận (Infinite Scroll):** Khi cuộn gần tới video cuối (`has_more == true`), tự động gọi `/api/videos/feed?cursor=...` để nối thêm video mới vào DOM.
- **Responsive trên điện thoại:**
  - Navbar thu gọn thành **1 dòng cao 52px** (chỉ giữ icon logo + menu vuốt ngang + chuông/nút tài khoản).
  - Khung Feed chiếm trọn `calc(100dvh - 52px)`, ẩn footer và khóa cuộn ngoài (`overflow: hidden`), tránh bị giật khung hình khi thao tác trên điện thoại.

---

### Task 4: UI Trang Đăng Video (`frontend/pages/upload.html`, `frontend/js/pages/upload.js`)

- **Kiểm tra ngay trên trình duyệt trước khi tải lên (tiết kiệm băng thông):**
  1. Kiểm tra đuôi/MIME file video (`video/mp4`, `video/webm`) và dung lượng ≤ `50 MB`.
  2. Nạp file vào thẻ `<video>` ẩn (tạo URL tạm `URL.createObjectURL(file)`), chờ sự kiện `loadedmetadata` để đọc `videoPlayer.duration`. Nếu dài quá **60 giây** → báo lỗi ngay không cho đăng.
- **Tự động cắt ảnh bìa (Thumbnail) từ video:**
  - Tua `videoPlayer.currentTime` tới khoảng `0.5s`, vẽ khung hình hiện tại lên thẻ `<canvas>` (`drawImage`), rồi xuất ra file ảnh JPEG (`canvas.toBlob`) làm thumbnail mặc định (người dùng vẫn có nút chụp khung hình khác hoặc tải ảnh riêng từ máy).
- **Chọn sản phẩm gắn vào video:** Nếu tài khoản là `SELLER`, tải danh sách sản phẩm đang bán của Shop để tích chọn tối đa 3 sản phẩm.
- **Tiến trình tải lên:** Dùng callback `onUploadProgress` của Axios để cập nhật thanh phần trăm `%` theo thời gian thực khi đẩy lên R2.

---

### Task 5: Lướt Video trên Hồ sơ & Quản lý Video của tôi (`profile.html`/`profile.js` & `my-videos.html`/`my-videos.js`)

- **Trang Hồ sơ (`profile.html`):**
  - Gọi `GET /api/videos/users/{user_id}` để hiển thị lưới video công khai của người dùng đó (hoặc của chính mình). Bấm vào từng ô video sẽ mở trang xem chi tiết `video.html?id=...` để lướt và tương tác.
- **Trang Quản lý Video của tôi (`my-videos.html`):**
  - Gọi `GET /api/videos/users/{my_id}?include_hidden=true` để xem tất cả video đã đăng (gồm cả video đang bị ẩn).
  - **Sửa mô tả:** Gọi `PATCH /api/videos/{video_id}` (backend kiểm tra `video.user_id == user.id` bằng `get_owned_video_for_update`).
  - **Xóa video:** Gọi `DELETE /api/videos/{video_id}` → xóa bản ghi trong DB (`video_products` tự xóa theo nhờ `CASCADE`), sau đó gọi `remove_uploaded_files(video_url, thumbnail_url)` để **xóa luôn cả file video và ảnh bìa trên Cloudflare R2**.

---

### Task 6: Gắn Sản phẩm vào Video (`POST /api/videos/{video_id}/products`, `GET /api/videos/{video_id}/products`)

Logic xử lý nằm ở `set_video_products()` trong `backend/app/crud/video.py`:
1. Kiểm tra video có tồn tại không (`404`) và người gọi API có phải chủ nhân video không (`403`).
2. Loại bỏ ID trùng (`dict.fromkeys(product_ids)`). Nếu số lượng > **3 sản phẩm** → báo lỗi `400` (*"Một video chỉ được gắn tối đa 3 sản phẩm"*).
3. Kiểm tra người dùng có cửa hàng (`Shop.owner_id == user_id`) không, và tất cả `product_id` truyền lên đều phải thuộc chính Shop đó (`Product.shop_id == shop.id`) và đang ở trạng thái `ACTIVE`.
4. Xóa liên kết cũ của video đó trong `video_products` và thêm các dòng mới (hoặc dùng `add_video_product` có khóa dòng `with_for_update()` để tránh race condition khi bấm nhanh 2 lần).

---

### Task 7: Lưu trữ Video & Ảnh trên Cloudflare R2 (`backend/app/core/storage.py`)

Hệ thống thiết kế theo mẫu **Strategy Pattern** (chung 1 giao diện `BaseStorage` với 2 hàm `save()` và `delete()`):

1. **`LocalStorage` (`STORAGE_DRIVER=local`):** Lưu file vào thư mục `backend/uploads/...` trên ổ đĩa máy tính (dùng khi dev offline hoặc chạy unit test).
2. **`R2Storage` (`STORAGE_DRIVER=r2`):**
   - Kết nối tới endpoint `https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com` bằng thư viện `boto3` (chuẩn AWS S3 API).
   - File được phân loại theo thư mục (prefix) trên bucket `clipshop-media`:
     - `videos/...` (video ngắn)
     - `covers/...` (ảnh bìa video)
     - `products/...` (ảnh sản phẩm)
     - `shops/...` (logo cửa hàng)
     - `avatars/...` (ảnh đại diện người dùng)
   - Cấu hình **CORS Policy** trên bucket R2 cho phép trình duyệt từ `https://clipshopai.phancopako.com` và `https://clipshop-ai-ojt.vercel.app` được phép gửi request `PUT`, `GET`, `HEAD`.
3. **Cơ chế ký URL hiển thị (`resolve_media_url`):**
   - Trong DB lưu đường dẫn chuẩn dạng `https://pub-...r2.dev/<key>`.
   - Vì đường dẫn `pub-...r2.dev` có thể bị chặn `401 Unauthorized` nếu bucket chưa mở public hoàn toàn, mỗi khi backend trả về `video_url`, `thumbnail_url`, `avatar_url`, `image_url`, hàm `resolve_media_url()` sẽ tự động dùng `boto3` tạo ra một **Presigned GET URL** có chữ ký HMAC-SHA256 (hiệu lực 3600 giây = 1 tiếng) trỏ trực tiếp tới `r2.cloudflarestorage.com`. Nhờ vậy trình duyệt luôn xem video và tải ảnh `200 OK` ổn định và bảo mật.
