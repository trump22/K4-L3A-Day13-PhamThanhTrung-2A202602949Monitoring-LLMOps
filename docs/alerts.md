# Alert runbook

Các alert dưới đây đo triệu chứng thấy được từ request và log. Kênh nhận thông báo là Slack `#llm-observability`.

## Alert 1: Latency P95 cao

- **Condition:** P95 `response_sent.latency_ms` vượt 3000 ms trong 10 phút.
- **Severity / owner:** High / LLMOps on-call.
- **Ảnh hưởng:** Người dùng nhận câu trả lời chậm, kể cả khi request vẫn thành công.

Kiểm tra theo thứ tự:

1. Mở panel Latency trên toàn bộ lịch sử, rồi tập trung vào thời điểm incident để đối chiếu P95, P99, TTFT P95 với threshold 3000 ms.
2. Lọc `response_sent` có `latency_ms > 3000`, lấy một `correlation_id`, rồi mở trace có cùng metadata.
3. So sánh thời gian observation `retrieval` và `llm.generate` để xác định bước tăng thời gian.

Mitigation: giảm concurrency hoặc tạm chuyển sang đường retrieval/cache khỏe; nếu generation là bước chậm, giảm độ dài context hoặc hạ giới hạn output. Xác nhận P95 trở lại dưới 3000 ms trong ít nhất 10 phút trước khi đóng alert.

## Alert 2: Error rate cao

- **Condition:** `request_failed / request_received` vượt 2% trong 5 phút.
- **Severity / owner:** Critical / API on-call.
- **Ảnh hưởng:** Một phần request không nhận được câu trả lời.

Kiểm tra theo thứ tự:

1. Mở panel Errors, kiểm tra error rate và breakdown theo `error_type`.
2. Lấy `correlation_id` của một `request_failed`; đối chiếu log `request_received` cùng ID và trace tương ứng.
3. Kiểm tra tỷ lệ retrieval success để phân biệt lỗi retrieval với lỗi ở các bước sau.

Mitigation: nếu lỗi tập trung ở retrieval, bật fallback/cache hoặc rollback cấu hình retriever gần nhất; nếu lỗi API tăng đồng đều, giảm traffic vào upstream và xử lý lỗi theo `error_type`. Đóng alert khi error rate không quá 2% trong 5 phút.

## Alert 3: Retrieval success thấp

- **Condition:** Tỷ lệ `tool_success == true` trên các event có `tool_success` thấp hơn 90% trong 10 phút.
- **Severity / owner:** High / Retrieval on-call.
- **Ảnh hưởng:** Câu trả lời thiếu context hoặc request thất bại trước khi gọi LLM.

Kiểm tra theo thứ tự:

1. Mở panel Errors và xác nhận retrieval success giảm, đồng thời xem `error_type` có tăng không.
2. Lọc log theo `tool_name=retrieval` và lấy một `correlation_id` lỗi hoặc chậm.
3. Mở trace cùng ID, kiểm tra duration/status của observation `retrieval` trước khi kiểm tra generation.

Mitigation: chuyển sang index dự phòng hoặc cache, giảm retry gây dồn tải và khôi phục kết nối vector store. Đóng alert khi retrieval success đạt ít nhất 90% trong 10 phút.
