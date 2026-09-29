# Báo cáo cá nhân — K4-L3A Day 13 Monitoring & LLMOps

> Mỗi học viên hoàn thiện một file duy nhất này. Khi dẫn evidence, dùng đường dẫn tương đối, ví dụ `evidence/07-trace-waterfall.png`.

## 1. Thông tin học viên

- **Họ và tên:** Phạm Thanh Trung
- **MSSV:** 2A202602949
- **Lớp:** K4-L3A
- **Repository URL:** https://github.com/trump22/K4-L3A-Day13-PhamThanhTrung-2A202602949Monitoring-LLMOps
- **Commit SHA cuối:** SHA cuối sẽ được cung cấp cùng kết quả nộp; Git không thể chứa hash tự tham chiếu của chính commit trong file này.
- **Challenge ID:** `day13-k4-l3a-monitoring-llmops-v1`

## 2. Evidence index

Điền đúng đường dẫn tới evidence thực tế. Có thể đổi tên hoặc dùng nhiều ảnh nếu cần.

| Evidence | Đường dẫn |
|---|---|
| Pytest cuối | `evidence/01-pytest.png` |
| Log validator | `evidence/02-log-validator.png` |
| Dashboard validator | `evidence/03-dashboard-validator.png` |
| Structured log | `evidence/04-structured-log.png` |
| PII redaction | `evidence/05-pii-redaction.png` |
| Trace list | `evidence/06-trace-list.png` |
| Trace waterfall | `evidence/07-trace-waterfall.png` |
| Trace metadata | `evidence/08-trace-metadata.png` |
| Prompt versions | `evidence/09-prompt-versions.png` |
| Prompt rollback | `evidence/10-prompt-rollback.png` |
| Dashboard runtime | `evidence/11-dashboard-overview.png` |
| Incident metric | `evidence/12-incident-metric.png` |
| Incident log | `evidence/13-incident-log.png` |
| Incident trace | Screenshot still needed; verified trace link in section 7 |



## 3. Kết quả kỹ thuật

| Nội dung | Baseline | Kết quả cuối | Nhận xét |
|---|---|---|---|
| `validate_logs.py` | 30/100 | 100/100 | Validator hiện đọc 182 records, 76 correlation IDs và phát hiện 0 PII; ảnh kết quả: `evidence/02-log-validator.png`. Baseline 30/100 không có ảnh trong evidence hiện tại. |
| `validate_dashboard.py` | — | 6/6 panel | `evidence/03-dashboard-validator.png`. |
| `pytest` | — | 25 passed | `evidence/01-pytest.png`. |
| Số traces hợp lệ | — | 65 root observations | Danh sách trong `evidence/06-trace-list.png`. |
| Số PII leak | 0 | 0 | Email, Vietnamese phone, CCCD, and payment-card values are redacted before JSON serialization. |
| Latency P95 / TTFT P95 | — | 4660 ms / 50 ms | Runtime window trong `evidence/11-dashboard-overview.png` và ảnh crop `evidence/12-incident-metric.png`; SLO P95 là 3000 ms. |
| Retrieval success rate | — | 100% | `evidence/11-dashboard-overview.png`. |

## 4. Logging và PII

- **Cách tạo/nhận và truyền correlation ID:** Middleware clears prior context, accepts `x-request-id` when supplied, otherwise creates `req-<8-hex>`, binds it to structlog, and returns it in the response header.
- **Các metadata được ghi vào structured log:** `user_id_hash`, `session_id`, `feature`, `model`, and `env` are bound before `request_received` and flow through the request logs.
- **Cách bảo đảm PII được scrub trước khi ghi:** The recursive `scrub_event` processor runs after exception formatting and before both the JSONL writer and final JSON renderer.
- **Cách kiểm chứng kết quả:** Lần kiểm tra cuối, validator đọc 182 records và 76 correlation IDs, không thiếu trường/context và không phát hiện PII; xem `evidence/02-log-validator.png`.

## 5. Tracing và prompt versioning

- **Cấu trúc root/retrieval/generation observations:** Root `lab-agent-run` có hai span con `retrieval` (`RETRIEVER`) và `llm.generate` (`GENERATION`). Trace thể hiện duration từng span; generation ghi model, usage và cost. Một số trace runtime dùng `local-fallback` khi prompt managed không khả dụng; xem `evidence/07-trace-waterfall.png` và `evidence/08-trace-metadata.png`.
- **Cách nối trace với log:** `correlation_id` is propagated into root and child metadata and written to API logs. Example: `req-00b4a4a0` links the log and trace `a7237aa9322db0d7ac3165c76ce97855`.
- **Prompt name:** `day13-chat`.
- **Version/label baseline:** v1 with `baseline` and `production`.
- **Version/label candidate:** v2 with `candidate`.
- **Trace ID của mỗi version:** v1 production baseline `a7237aa9322db0d7ac3165c76ce97855`; v2 candidate `498502edb087420860edbebc27c01292`; v2 production `ea4ea716acba3858649f7c613cec2eaf`; v1 rollback `ebb7badbe333b0f49519297f6c442432`.
- **Cách promote và rollback `production`:** `production` was promoted to v2, verified by trace `ea4ea716acba3858649f7c613cec2eaf`, then rolled back to v1 and verified by `ebb7badbe333b0f49519297f6c442432`; see `evidence/10-prompt-rollback.png`.

## 6. Dashboard, SLO và alerts

- **Dashboard và sáu panel:** Streamlit dashboard trong `dashboard.py` đọc `data/logs.jsonl` và hiển thị sáu panel. Ảnh runtime: `evidence/11-dashboard-overview.png`.
- **SLO và lý do chọn:** 99.5% request must finish successfully within 3000 ms over 28 days. The threshold is above the clean baseline P95 while still representing noticeable user delay.
- **Cách tính error budget:** 0.5% of all requests in the 28-day window, equivalent to 50 bad requests per 10,000 requests. Failures and responses slower than 3000 ms consume the budget.
- **Ba alert và runbook tương ứng:** High latency P95 (10m), critical error rate (5m), and low retrieval success (10m), each with Slack channel, owner, and mitigation in `docs/alerts.md`.

## 7. Điều tra challenge

- **Challenge ID:** `day13-k4-l3a-monitoring-llmops-v1` (K4, seed 1311), incident `rag_slow`.
- **Khoảng thời gian điều tra:** Batch chính thức dùng làm evidence metric → log → trace chạy 2026-09-29 22:03:06–22:03:25 Asia/Bangkok (15:03:06–15:03:25 UTC). Đây là run `day13-k4-l3a-monitoring-llmops-v1`, cohort K4, seed 1311.
- **Triệu chứng từ metrics:** Trong ảnh dashboard runtime `evidence/11-dashboard-overview.png`, có 59 request, P50/P95/P99 `2160/4660/4671 ms`, TTFT P95 `50 ms`; P95 vượt SLO 3000 ms và cả 5 request challenge đều vượt ngưỡng challenge 2000 ms. Ảnh crop là `evidence/12-incident-metric.png`. Dashboard dùng toàn bộ lịch sử `data/logs.jsonl`, không phải riêng cohort.
- **Log line và correlation ID liên quan:** `data/logs.jsonl`, event `response_sent`, session `k4-l3a-challenge-s03`, correlation ID `req-6a4e9b45`, `latency_ms=4664`, `tool_name=retrieval`, `tool_success=true`; timestamp `2026-09-29T15:03:25.192838Z`. Ảnh chụp bảng log là `evidence/13-incident-log.png`.
- **Trace ID và span gây ảnh hưởng:** [Trace Langfuse `f6a807f1588f4cccecdbc5693ee5f262`](https://cloud.langfuse.com/project/cmumb79c61xbiad0fshp5gams/traces/f6a807f1588f4cccecdbc5693ee5f262) có `correlation_id=req-6a4e9b45`; root `lab-agent-run` kéo dài `4.664 s`, child `retrieval` `2.50 s`, `llm.generate` `0.15 s`. Trace đã xác thực trong đúng project Langfuse. Screenshot trace `evidence/14-incident-trace.png` chưa có; ảnh cùng tên trước đó thuộc project khác đã được chuyển khỏi evidence sang `submission/quarantine/`.
- **Rerun xác minh sau khi sửa concurrency:** Ngày 2026-09-30 00:15:06–00:15:13 Asia/Bangkok, chạy lại đúng challenge với `--concurrency 5`. Sau khi restart API, `/metrics` chỉ có 5 request challenge: P50 `4711 ms`, P95/P99 `4719 ms`, TTFT P95 `50 ms`, retrieval success `100%`, không có lỗi. Correlation ID mới `req-0521bcf0` khớp [trace `ab61f6d3fdd0597d2a98fe092efc03f6`](https://cloud.langfuse.com/project/cmumb79c61xbiad0fshp5gams/traces/ab61f6d3fdd0597d2a98fe092efc03f6): root `4.72 s`, retrieval `2.51 s`, generation `0.16 s`, cost `$0.002805`.
- **Root cause:** Scenario `rag_slow` chèn `time.sleep(2.5)` trong `app/mock_rag.py::retrieve`; trace xác nhận retrieval là span chậm nhất và chiếm phần lớn latency tăng thêm. Correlation ID trong log và trace xác nhận cùng request.
- **Fix action:** Incident đã tắt qua `scripts/inject_incident.py --disable`; `/health` xác nhận cả ba incident đều `false`. `/chat` đã chuyển `LabAgent.run` đồng bộ sang thread pool; lần rerun concurrent hoàn tất trong khoảng 8 giây thay vì gần 23 giây.
- **Preventive measure:** Duy trì alert P95/retrieval success và runbook tại `docs/alerts.md`; đặt timeout/deadline cho retrieval và theo dõi retrieval duration theo span. Prompt fetch có thể fallback `local-v1`; Cloud Metrics API dashboard hiện lỗi `ApiError`, trong khi dashboard vẫn dùng log JSONL làm nguồn metric.

## 8. Giải thích và tự đánh giá

- **Một quyết định kỹ thuật quan trọng và lý do:** Dùng cùng correlation ID xuyên middleware, structured logs và span metadata để có thể nối tín hiệu tổng quan với request cụ thể.
- **Một lỗi/blocker đã gặp:** Một số trace cho thấy `prompt_source=local-fallback`, nên không thể mặc định mọi request đều lấy được managed prompt từ Langfuse.
- **Cách tìm nguyên nhân và xử lý:** So sánh P95/P99 với SLO, tìm request latency cao trong JSONL, rồi mở trace cùng correlation ID; duration retrieval lớn nhất chỉ ra khu vực cần xử lý. Sau điều tra, tắt incident giả lập và kiểm tra trạng thái health.
- **Cách hiểu luồng Metrics → Logs → Traces:** Metrics phát hiện tail latency; correlation ID định vị log của request; trace phân rã thời gian thành retrieval và generation để xác định span gây chậm.
- **Vai trò của prompt version, token/cost, SLO hoặc rollback trong vận hành LLM:** Version/label giúp truy xuất và rollback prompt; token/cost giúp theo dõi tác động chi phí; SLO/error budget lượng hóa mức ảnh hưởng và hỗ trợ quyết định mitigation.
- **Điều quan trọng nhất đã học:** Một chỉ số bất thường chỉ có ích khi nối được với log và trace của cùng request.
- **Hạn chế hoặc phần chưa hoàn thành, nếu có:** Screenshot waterfall CP3 cùng project Langfuse còn cần chụp/lưu thành `evidence/14-incident-trace.png`; file ảnh sai project đã được chuyển sang `submission/quarantine/` để tránh nộp nhầm. Trace/correlation đã được xác thực bằng link và metadata trong section 7.

## 9. Checklist trước khi nộp

- [x] Source, report và evidence hiện có được đóng gói trong commit cuối.
- [x] Các ảnh được dẫn trong report mở được bằng đường dẫn tương đối.
- [ ] Lưu screenshot Langfuse của trace CP3 đúng project dưới `evidence/14-incident-trace.png`; trace/correlation đã được xác thực bằng link trong report.
- [x] Metric → log → trace đã được nối bằng `req-6a4e9b45`.
- [x] Tests và validators đã chạy thành công; cách chạy lại xem README.
- [x] Thư mục evidence không còn ảnh trace của project khác; bản sai đã được chuyển sang `submission/quarantine/`.
- [ ] URL repo và commit SHA cuối đã được nộp trên LMS/Codelabs (cần commit cuối trước khi nộp).
