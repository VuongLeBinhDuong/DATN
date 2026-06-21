# Báo cáo Đánh giá RAG sử dụng Ragas

**Tổng số câu hỏi kiểm thử:** 3
**Thời gian thực hiện:** 2026-06-20

## Chỉ số Trung bình (Aggregate Metrics)

| Chỉ số | Điểm số (0.0 - 1.0) | Ý nghĩa lâm sàng |
| :--- | :--- | :--- |
| **Faithfulness** | 0.0000 | Độ trung thực của câu trả lời so với tài liệu y học (Tránh ảo tưởng) |
| **Answer Relevancy** | 0.0000 | Độ liên quan, trực diện của câu trả lời với câu hỏi lâm sàng |
| **Context Precision** | 0.0000 | Độ chính xác của các đoạn văn bản y khoa được truy xuất |
| **Context Recall** | 0.0000 | Độ đầy đủ của các tài liệu y học được truy xuất so với đáp án chuẩn |

## Chi tiết từng câu hỏi (Detailed Results)

### Câu 1: bệnh tiểu đường tuýp 2 là gì và cách điều trị cơ bản

**Ngữ cảnh truy xuất (Contexts):**
- # Bệnh tiểu đường ở người Việt và người nước ngoài có giống nhau không?

Câu hỏi: Bệnh tiểu đường ở người Việt và người nước ngoài có giống nhau không...
- # Mắt kém do tiểu đường tuýp 2 cần điều trị thế nào?

Câu hỏi: Mắt kém do tiểu đường tuýp 2 cần điều trị thế nào?

Trả lời: Bố của bạn bị mắc bệnh tiể...
- # Tôi 62 tuổi, tiểu đường tuýp 2 đã điều trị ổn định, từng sốc nặng với nhóm thuốc B: b1, b6, b12. Từng sốc hôn mê với một loại thuốc kháng sinh (lúc ...
- # Đường máu 22.3 có dễ gây biến chứng không? Nên kiêng những gì và sử dụng thuốc nào điều trị tiểu đường?

Câu hỏi: Đường máu 22.3 có dễ gây biến chứn...
- # Hôn mê do biến chứng tiểu đường, nhịp tim, đường huyết ổn định có khả năng tỉnh lại và điều trị không?

Câu hỏi: Hôn mê do biến chứng tiểu đường, nh...
- # Tôi bị K (tuyến tiền liệt) 6 năm điều trị ngoại trú, tiểu đường tuýp 2, huyết áp hơi cao. Xin hỏi có được chích vaccine Covid-19 không? Nếu được đăn...
- # Tôi 62 tuổi, có bệnh nền tăng huyết áp và tiểu đường tuýp 2. Thỉnh thoảng tôi bị dị ứng thời tiết khi lạnh tứ chi. Vậy tôi có tiêm vaccine Covid-19 ...
- số HbA1c < 6. 5% có nghĩa đường máu của bạn đang được kiểm soát tốt, điều này có nghĩa có thể làm chậm và ngăn ngừa sự phát triển các biến chứng về mắ...

**Đáp án chuẩn (Ground Truth):**
> Đái tháo đường típ 2 là bệnh rối loạn chuyển hóa glucose đặc trưng bởi tình trạng đề kháng insulin hoặc giảm tiết insulin tương đối. Điều trị cơ bản bao gồm thay đổi lối sống (ăn kiêng giảm tinh bột, tăng vận động thể lực) và sử dụng thuốc hạ đường huyết đường uống như Metformin hoặc tiêm insulin khi cần thiết.

**Hệ thống trả lời (Generated Answer):**
> **Bệnh tiểu đường tuýp 2 là gì và cách điều trị cơ bản**

Bệnh tiểu đường tuýp 2 (hay còn gọi là đái tháo đường type 2) là một tình trạng sức khỏe khi cơ thể không sản xuất đủ insulin hoặc không sử dụng insulin hiệu quả. Điều này dẫn đến sự tăng lên của đường huyết trong máu.

Cách điều trị bệnh tiểu đường tuýp 2 thường bao gồm:

* **Thay đổi lối sống**: Ăn uống lành mạnh, tập thể dục đều đặn, giảm cân nếu cần thiết.
* **Sử dụng thuốc**: Thuốc insulin hoặc thuốc khác giúp tăng cường khả năng sử dụng insulin của cơ thể.
* **Quản lý đường huyết**: Kiểm tra mức đường huyết thường xuyên và điều chỉnh chế độ ăn uống và sử dụng thuốc để duy trì mức đường huyết trong tầm kiểm soát.

Ngoài ra, người bệnh tiểu đường tuýp 2 cũng cần chú ý đến các biến chứng tiềm ẩn như bệnh tim mạch, đột quỵ, và tổn thương mắt.

**Tham khảo chung**: Nếu bạn đang bị bệnh tiểu đường tuýp 2, hãy tham khảo ý kiến của bác sĩ để được tư vấn cụ thể về cách điều trị và quản lý tình trạng sức khỏe của mình.

---

### Câu 2: công dụng của thuốc paracetamol và liều lượng hạ sốt thông thường

**Ngữ cảnh truy xuất (Contexts):**
- # Buồn nôn sau uống Panadol 1 tuần là sao?

Câu hỏi: Buồn nôn sau uống Panadol 1 tuần là sao?

Trả lời: Paracetamol là loại thuốc giảm đau hạ sốt phổ ...
- # Uống thuốc Panadol nhiều trong 1 lần có sao không?

Câu hỏi: Uống thuốc Panadol nhiều trong 1 lần có sao không?

Trả lời: Panadol chứa Paracetamol l...
- ếu sử dụng với liều nhỏ hơn 100mg thì nồng độ thuốc trong sữa mẹ không đáng kể. Với liều thuốc bạn sử dụng (2 viên) bạn vẫn có thể cho bé bú sữa mẹ bì...
- # Bị cảm lạnh, nóng trong người phải làm sao?

Câu hỏi: Bị cảm lạnh, nóng trong người phải làm sao?

Trả lời: Các triệu chứng của bạn trong bệnh cảm l...
- không?

Trả lời: Với tất cả đối tượng tham gia tiêm vaccine Covid-19, các bác sĩ sẽ tiến hành khám sàng lọc, kiểm tra sức khỏe và tư vấn cách chăm sóc...
- o vậy việc đi khám tâm lý ở lứa tuổi 11 tháng này là không cần thiết, bạn cần chú ý dùng hạ sốt sớm cho bé khi sốt ( Nhiệt độ >= 38 độ bắt đầu dùng hạ...

**Đáp án chuẩn (Ground Truth):**
> Paracetamol (Acetaminophen) là thuốc giảm đau và hạ sốt phổ biến. Liều lượng thông thường cho người lớn là 500mg - 1000mg mỗi 4-6 giờ, tối đa không quá 4g một ngày để tránh tổn thương gan nặng.

**Hệ thống trả lời (Generated Answer):**
> **Công dụng của thuốc Paracetamol và liều lượng hạ sốt thông thường**

Thuốc Paracetamol là một loại thuốc giảm đau, hạ sốt phổ biến. Công dụng chính của thuốc này là:

* Giảm đau nhẹ đến vừa
* Hạ sốt hiệu quả

Liều lượng sử dụng của thuốc Paracetamol để hạ sốt thông thường như sau:

* Người lớn: 500-1000 mg mỗi lần, uống 4-6 lần một ngày
* Trẻ em: Liều lượng tùy thuộc vào tuổi và cân nặng của trẻ. Thông thường là 120-250 mg/m2 mỗi lần, uống 4-6 lần một ngày.

Lưu ý: Khi sử dụng thuốc Paracetamol, bạn nên đọc kỹ hướng dẫn sử dụng và tuân thủ liều lượng khuyến cáo để tránh tác dụng phụ không mong muốn.

Ngoài ra, khi sốt cao (trên 38 độ C), người bệnh có thể uống thuốc hạ sốt như Paracetamol để giảm nhiệt độ cơ thể. Tuy nhiên, nếu sốt nhẹ (dưới 38 độ C), bạn nên sử dụng các biện pháp hạ sốt khác như tắm nước lạnh, uống nhiều nước, hoặc sử dụng máy tạo ẩm.

**Tham khảo chung**

Khi sử dụng thuốc Paracetamol, bạn nên đọc kỹ hướng dẫn sử dụng và tuân thủ liều lượng khuyến cáo để tránh tác dụng phụ không mong muốn. Nếu có bất kỳ câu hỏi nào về việc sử dụng thuốc này, bạn nên tham khảo ý kiến của bác sĩ hoặc dược sĩ.

**Nguồn**

* [1] chunk_id=chunk_5d51092800a717a5, doc=doc_vihealthqa_test_206
* [2] chunk_id=chunk_9ee97c96c37d4bcc, doc=doc_vihealthqa_train_5116

---

### Câu 3: metformin có tác dụng gì trong điều trị tiểu đường

**Ngữ cảnh truy xuất (Contexts):**
- # Tôi mắc bệnh tiểu đường type 2, cách đây 7 năm tôi bị giảm tiểu cầu vô căn cấp tính điều trị một tuần thì khỏi, hàng năm kiểm tra đều trên 150. Tôi ...
- # Tôi năm nay 39 tuổi, tiền sử bệnh tiểu đường type 2 (hơn 3 năm). Tôi còn bị men gan cao, rối loạn thần kinh, rối loạn lipid máu, rối loạn nhịp tim (...
- # Cảnh báo và lưu ý khi sử dụng bút tiêm cho bệnh nhân đái tháo đường type 2?

Câu hỏi: Cảnh báo và lưu ý khi sử dụng bút tiêm cho bệnh nhân đái tháo ...
- # Cải thiện tình trạng đau bụng sau khi uống thuốc điều trị hen suyễn, dị ứng như thế nào?

Câu hỏi: Cải thiện tình trạng đau bụng sau khi uống thuốc ...
- # Cách chăm sóc trẻ sốt phát ban tại nhà

Câu hỏi: Cách chăm sóc trẻ sốt phát ban tại nhà

Trả lời: Trường hợp con anh/chị đã khám và được bác sĩ chẩn...
- à hiện tại chỉ điều trị đái tháo đường type 2 trong giai đoạn ổn định, như vậy bác hoàn toàn có thể được tiêm ngừa vaccine Covid-19. Trước khi tiêm, b...
- # Sỏi tiết niệu có kích thước lớn có để lại biến chứng nguy hiểm gì không?

Câu hỏi: Sỏi tiết niệu có kích thước lớn có để lại biến chứng nguy hiểm gì...
- # Hiện tại em đang điều trị HIV bằng ARV được 4 năm. CD4 đã ổn định và tải lượng dưới ngưỡng phát hiện.Là người nhiều kinh nghiệm trong lĩnh vực HIV, ...

**Đáp án chuẩn (Ground Truth):**
> Metformin thuộc nhóm Biguanide, là lựa chọn đầu tay trong điều trị đái tháo đường típ 2. Cơ chế hoạt động là làm giảm sản xuất glucose ở gan, giảm hấp thu glucose ở ruột và tăng nhạy cảm với insulin ở các mô ngoại vi.

**Hệ thống trả lời (Generated Answer):**
> **Tác dụng của Metformin trong điều trị tiểu đường**

Metformin là một loại thuốc dùng để điều trị bệnh tiểu đường loại 2. Thuốc này giúp giảm lượng glucose trong máu bằng cách tăng cường độ nhạy cảm với insulin và cải thiện khả năng sử dụng glucose của cơ thể.

Trong điều trị tiểu đường, metformin thường được sử dụng kết hợp với chế độ ăn uống và tập luyện để kiểm soát mức đường huyết. Thuốc này có thể giúp giảm nguy cơ biến chứng liên quan đến tiểu đường, chẳng hạn như bệnh tim mạch và suy thận.

Tuy nhiên, cần lưu ý rằng metformin không phải là thuốc điều trị tiểu đường loại 1, mà chỉ được sử dụng cho người mắc bệnh tiểu đường loại 2. Nếu bạn đang dùng metformin để điều trị tiểu đường, hãy tuân thủ hướng dẫn của bác sĩ về liều lượng và thời gian uống.

**Lưu ý quan trọng**

* Metformin không phải là thuốc điều trị tiểu đường loại 1.
* Thuốc này chỉ được sử dụng cho người mắc bệnh tiểu đường loại 2.
* Hãy tuân thủ hướng dẫn của bác sĩ về liều lượng và thời gian uống metformin.
* Nếu bạn có bất kỳ vấn đề sức khỏe nào, hãy tham khảo ý kiến của bác sĩ trước khi dùng metformin.

**Tham khảo chung**

Nếu bạn muốn biết thêm thông tin về metformin hoặc cần tư vấn về việc sử dụng thuốc này, hãy tham khảo ý kiến của bác sĩ hoặc chuyên gia y tế.

---
