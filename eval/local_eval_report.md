# Báo cáo Đánh giá RAG Cục bộ (Local NLP Benchmark)

**Tổng số câu hỏi kiểm thử:** 10
**Định dạng:** 100% Offline (Không phụ thuộc LLM ngoài)

## Chỉ số Trung bình (Aggregate Metrics)

| Chỉ số | Điểm số (0.0 - 1.0) | Ý nghĩa đánh giá |
| :--- | :--- | :--- |
| **SBERT Similarity** | 0.7463 | Độ tương đồng ngữ nghĩa của câu trả lời sinh ra so với đáp án chuẩn |
| **ROUGE-L** | 0.1303 | Mức độ giữ chuỗi con chung dài nhất (đo độ phủ thông tin từ vựng) |
| **BLEU-4** | 0.0257 | Tỷ lệ trùng khớp các cụm từ (đo độ tự nhiên của câu chữ) |

## Chi tiết từng câu hỏi (Detailed Results)

### Câu 1: bệnh tiểu đường tuýp 2 là gì và cách điều trị cơ bản

**Chỉ số đo đạc:**
- Semantic Similarity: **0.8304**
- ROUGE-L: **0.1588**
- BLEU-4: **0.0295**

**Ngữ cảnh truy xuất (Contexts):**
- # Bệnh tiểu đường ở người Việt và người nước ngoài có giống nhau không?

Câu hỏi: Bệnh tiểu đường ở người Việt và người ...
- # Mắt kém do tiểu đường tuýp 2 cần điều trị thế nào?

Câu hỏi: Mắt kém do tiểu đường tuýp 2 cần điều trị thế nào?

Trả l...
- # Tôi 62 tuổi, tiểu đường tuýp 2 đã điều trị ổn định, từng sốc nặng với nhóm thuốc B: b1, b6, b12. Từng sốc hôn mê với m...

**Đáp án chuẩn (Ground Truth):**
> Đái tháo đường típ 2 là bệnh rối loạn chuyển hóa glucose đặc trưng bởi tình trạng đề kháng insulin hoặc giảm tiết insulin tương đối. Điều trị cơ bản bao gồm thay đổi lối sống (ăn kiêng giảm tinh bột, tăng vận động thể lực) và sử dụng thuốc hạ đường huyết đường uống như Metformin hoặc tiêm insulin khi cần thiết.

**Hệ thống trả lời (Generated Answer):**
> **Bệnh tiểu đường tuýp 2 là gì và cách điều trị cơ bản**

Tiểu đường tuýp 2 (hay còn gọi là đái tháo đường type 2) là một bệnh lý về đường huyết, trong đó cơ thể không sản xuất đủ insulin hoặc không sử dụng insulin hiệu quả. Điều này dẫn đến tăng đường huyết trong máu.

**Cách điều trị cơ bản**

Để điều trị tiểu đường tuýp 2, cần thực hiện các biện pháp sau:

1. **Thay đổi lối sống**: Ăn uống lành mạnh, tập thể dục thường xuyên, giảm cân nếu thừa cân.
2. **Sử dụng thuốc**: Thuốc insulin hoặc thuốc hạ đường huyết khác để kiểm soát đường huyết.
3. **Kiểm soát bệnh lý nền**: Điều trị các bệnh lý nền như tăng huyết áp, mỡ máu cao.

**Lưu ý**

* Tiểu đường tuýp 2 không thể chữa khỏi, nhưng có thể kiểm soát được bằng cách thực hiện các biện pháp trên.
* Cần theo dõi chặt chẽ tình trạng đường huyết và làm xét nghiệm định kỳ để điều chỉnh phương pháp điều trị.

**Tham khảo chung**

Nếu bạn đang bị tiểu đường tuýp 2, hãy tham khảo ý kiến của bác sĩ hoặc chuyên gia y tế để được tư vấn cụ thể về cách điều trị.

---

### Câu 2: công dụng của thuốc paracetamol và liều lượng hạ sốt thông thường

**Chỉ số đo đạc:**
- Semantic Similarity: **0.7538**
- ROUGE-L: **0.1238**
- BLEU-4: **0.0164**

**Ngữ cảnh truy xuất (Contexts):**
- # Buồn nôn sau uống Panadol 1 tuần là sao?

Câu hỏi: Buồn nôn sau uống Panadol 1 tuần là sao?

Trả lời: Paracetamol là l...
- # Uống thuốc Panadol nhiều trong 1 lần có sao không?

Câu hỏi: Uống thuốc Panadol nhiều trong 1 lần có sao không?

Trả l...
- ếu sử dụng với liều nhỏ hơn 100mg thì nồng độ thuốc trong sữa mẹ không đáng kể. Với liều thuốc bạn sử dụng (2 viên) bạn ...

**Đáp án chuẩn (Ground Truth):**
> Paracetamol (Acetaminophen) là thuốc giảm đau và hạ sốt phổ biến. Liều lượng thông thường cho người lớn là 500mg - 1000mg mỗi 4-6 giờ, tối đa không quá 4g một ngày để tránh tổn thương gan nặng.

**Hệ thống trả lời (Generated Answer):**
> **Công dụng của thuốc paracetamol và liều lượng hạ sốt thông thường**

Thuốc paracetamol là một loại thuốc giảm đau, hạ sốt phổ biến. Công dụng chính của thuốc này là:

* Giảm đau đầu, đau cơ bắp, đau răng
* Hạ sốt hiệu quả

Liều lượng sử dụng thuốc paracetamol để hạ sốt thông thường như sau:

* Người lớn: 500-1000 mg mỗi lần, uống 4-6 lần một ngày
* Trẻ em: Liều lượng tùy thuộc vào tuổi và cân nặng của trẻ. Thông thường là 120-180 mg/kg mỗi lần, uống 4-6 lần một ngày

Tuy nhiên, cần lưu ý rằng liều lượng trên chỉ mang tính chất tham khảo. Người dùng nên đọc kỹ hướng dẫn sử dụng thuốc và tuân theo khuyến cáo của bác sĩ.

Ngoài ra, khi sử dụng thuốc paracetamol, người dùng cũng cần chú ý đến các tác dụng phụ có thể xảy ra như:

* Buồn nôn
* Nôn
* Đau bụng
* Sưng mặt

Nếu gặp phải bất kỳ tác dụng phụ nào, người dùng nên dừng sử dụng thuốc và tham khảo ý kiến của bác sĩ.

**Tham khảo chung**

Khi sử dụng thuốc paracetamol để hạ sốt, người dùng cần lưu ý rằng:

* Thuốc chỉ có hiệu quả khi được sử dụng đúng liều lượng và thời gian.
* Không nên lạm dụng thuốc hoặc sử dụng quá lâu.
* Cần đọc kỹ hướng dẫn sử dụng thuốc và tuân theo khuyến cáo của bác sĩ.

Hy vọng thông tin trên sẽ giúp người dùng hiểu rõ hơn về công dụng và cách sử dụng thuốc paracetamol.

---

### Câu 3: metformin có tác dụng gì trong điều trị tiểu đường

**Chỉ số đo đạc:**
- Semantic Similarity: **0.8275**
- ROUGE-L: **0.1143**
- BLEU-4: **0.0100**

**Ngữ cảnh truy xuất (Contexts):**
- # Tôi mắc bệnh tiểu đường type 2, cách đây 7 năm tôi bị giảm tiểu cầu vô căn cấp tính điều trị một tuần thì khỏi, hàng n...
- # Tôi năm nay 39 tuổi, tiền sử bệnh tiểu đường type 2 (hơn 3 năm). Tôi còn bị men gan cao, rối loạn thần kinh, rối loạn ...
- # Cảnh báo và lưu ý khi sử dụng bút tiêm cho bệnh nhân đái tháo đường type 2?

Câu hỏi: Cảnh báo và lưu ý khi sử dụng bú...

**Đáp án chuẩn (Ground Truth):**
> Metformin thuộc nhóm Biguanide, là lựa chọn đầu tay trong điều trị đái tháo đường típ 2. Cơ chế hoạt động là làm giảm sản xuất glucose ở gan, giảm hấp thu glucose ở ruột và tăng nhạy cảm với insulin ở các mô ngoại vi.

**Hệ thống trả lời (Generated Answer):**
> **Tác dụng của Metformin trong điều trị tiểu đường**

Metformin là một loại thuốc được sử dụng để điều trị bệnh tiểu đường loại 2. Nó giúp giảm lượng đường trong máu bằng cách tăng cường khả năng sử dụng glucose của cơ thể.

Theo [1], khi điều trị tiểu đường, nếu xuống cân có thể do tác dụng phụ của thuốc tiểu đường. Vì vậy, nếu đang dùng Metformin và xuống cân, bạn nên tham khảo ý kiến bác sĩ để được tư vấn phù hợp.

Ngoài ra, theo [3], đối với người bị tiểu đường type 2, nếu đã được điều trị ổn định với chỉ số đường dưới 7 mmol/l trong vòng hơn 3 tháng mà không thay đổi liều lượng thuốc vẫn tiêm vaccine Covid-19.

---

### Câu 4: triệu chứng cảnh báo cơn tăng huyết áp cấp cứu nguy hiểm

**Chỉ số đo đạc:**
- Semantic Similarity: **0.6952**
- ROUGE-L: **0.1005**
- BLEU-4: **0.0325**

**Ngữ cảnh truy xuất (Contexts):**
- # Ở nhà và hạn chế vận động, uống nhiều nước có khỏi sốt xuất huyết không?

Câu hỏi: Ở nhà và hạn chế vận động, uống nhi...
- # Sốt xuất huyết Dengue thì có nên điều trị tại nhà không?

Câu hỏi: Sốt xuất huyết Dengue thì có nên điều trị tại nhà k...
- iểu cầu, đau bụng vùng gan, nôn, men gan tăng cao, tràn dịch màng bụng, màng phổi, . . . . . . Vì vậy khi sốt xuất huyết...

**Đáp án chuẩn (Ground Truth):**
> Các triệu chứng cảnh báo cơn tăng huyết áp nguy hiểm bao gồm đau đầu dữ dội, hoa mắt, chóng mặt, tức ngực, khó thở, suy giảm thị lực, nôn mửa hoặc lú lẫn. Đây có thể là dấu hiệu tổn thương cơ quan đích như đột quỵ hoặc nhồi máu cơ tim.

**Hệ thống trả lời (Generated Answer):**
> **Triệu chứng cảnh báo cơn tăng huyết áp cấp cứu nguy hiểm**

Câu hỏi của bạn liên quan đến các triệu chứng cảnh báo cơn tăng huyết áp cấp cứu nguy hiểm. Dựa trên ngữ cảnh đã được cung cấp, tôi sẽ tập trung vào các dấu hiệu và nguyên nhân có thể dẫn đến tình trạng này.

**Dấu hiệu cảnh báo cơn tăng huyết áp cấp cứu**

Một số dấu hiệu cảnh báo cơn tăng huyết áp cấp cứu bao gồm:

* Nhức mắt
* Chóng mặt
* Mất thị giác tạm thời
* Sưng mắt
* Đau đầu dữ dội

Nếu bạn đang gặp phải một hoặc nhiều trong những triệu chứng này, hãy ngay lập tức tìm kiếm sự giúp đỡ y tế.

**Nguyên nhân cơn tăng huyết áp cấp cứu**

Cơ thể có thể phản ứng với các tình trạng sức khỏe khác nhau bằng cách gây ra cơn tăng huyết áp cấp cứu. Một số nguyên nhân bao gồm:

* Tăng nhãn áp cấp tính
* Viêm não
* Rối loạn đông máu
* Độc chất

Nếu bạn đang gặp phải một trong những tình trạng này, hãy tìm kiếm sự giúp đỡ y tế ngay lập tức.

**Lưu ý quan trọng**

Cơn tăng huyết áp cấp cứu là một tình trạng sức khỏe nghiêm trọng và cần được điều trị kịp thời. Nếu bạn đang gặp phải các triệu chứng cảnh báo cơn tăng huyết áp cấp cứu, hãy tìm kiếm sự giúp đỡ y tế ngay lập tức.

**Tham khảo chung**

Nếu bạn muốn biết thêm thông tin về các dấu hiệu và nguyên nhân của cơn tăng huyết áp cấp cứu, vui lòng tham khảo các nguồn tài liệu sau:

* Tác giả: [Nguồn: ...]
* Nguồn: [Nguồn: ...]

Hãy nhớ rằng đây chỉ là một số thông tin chung và không phải là lời khuyên y tế cụ thể. Nếu bạn đang gặp phải các triệu chứng cảnh báo cơn tăng huyết áp cấp cứu, hãy tìm kiếm sự giúp đỡ y tế ngay lập tức.

---

### Câu 5: phác đồ điều trị viêm gan B mãn tính cơ bản là gì

**Chỉ số đo đạc:**
- Semantic Similarity: **0.6474**
- ROUGE-L: **0.1053**
- BLEU-4: **0.0285**

**Ngữ cảnh truy xuất (Contexts):**
- àm là bạn em cần làm xét nghiệm HBsAg xem đã bị nhiễm không và làm xét nghiệm HBsAb xem trong máu có kháng thể kháng vir...
- bản đồ, thường lành lại ở một khu vực và sau đó lại lan sang phần khác của lưỡi. Bệnh còn được gọi là viêm lưỡi di trú l...
- i có phải do bệnh viêm gan B tiến triển hay không? Từ kết quả đó, các bác sĩ sẽ thăm khám và đưa ra phác đồ điều trị hiệ...

**Đáp án chuẩn (Ground Truth):**
> Điều trị viêm gan B mãn tính chủ yếu nhằm ức chế sự nhân lên của virus HBV. Các thuốc kháng virus (nhóm Nucleot(s)ide analogs) thường dùng là Tenofovir (TDF hoặc TAF) hoặc Entecavir, cần dùng lâu dài và tuân thủ nghiêm ngặt dưới sự chỉ dẫn của bác sĩ chuyên khoa.

**Hệ thống trả lời (Generated Answer):**
> **Phác đồ điều trị viêm gan B mãn tính cơ bản**

Viêm gan B là một bệnh nhiễm trùng do virus viêm gan B (HBV) gây ra. Phác đồ điều trị viêm gan B mãn tính cơ bản bao gồm các bước sau:

1. **Chẩn đoán**: Trước khi bắt đầu điều trị, cần phải chẩn đoán chính xác tình trạng của bệnh nhân thông qua xét nghiệm máu.
2. **Điều trị dự phòng**: Đối với những người có nguy cơ cao bị nhiễm HBV, có thể được khuyến cáo sử dụng thuốc dự phòng như Hepatitis B Immune Globulin (HBIG) và vắc-xin viêm gan B để ngăn ngừa nhiễm trùng.
3. **Điều trị triệu chứng**: Nếu bệnh nhân đã bị nhiễm HBV, phác đồ điều trị sẽ tập trung vào việc giảm nhẹ các triệu chứng và ngăn ngừa tiến triển của bệnh.
4. **Thuốc điều trị**: Các thuốc chính được sử dụng để điều trị viêm gan B bao gồm:
	* Entecavir (Baraclude)
	* Tenofovir disoproxil fumarate (Viread)
	* Adefovir dipivoxil (Hepsera)

Lưu ý: Phác đồ điều trị có thể thay đổi tùy thuộc vào tình trạng cụ thể của bệnh nhân và nên được thực hiện dưới sự giám sát của bác sĩ.

**Tham khảo chung**

Viêm gan B là một bệnh nhiễm trùng nghiêm trọng và cần được điều trị kịp thời để ngăn ngừa tiến triển của bệnh. Nếu bạn nghi ngờ mình hoặc người thân có nguy cơ bị nhiễm HBV, hãy liên hệ với bác sĩ để được tư vấn và chẩn đoán chính xác.

**Nguồn**

* Trung tâm Kiểm soát và Phòng ngừa Dịch bệnh (CDC) Hoa Kỳ
* Tổ chức Y tế Thế giới (WHO)
* Các tài liệu y khoa khác

---

### Câu 6: hen suyễn là gì và cách sử dụng salbutamol khi lên cơn hen

**Chỉ số đo đạc:**
- Semantic Similarity: **0.8027**
- ROUGE-L: **0.0947**
- BLEU-4: **0.0035**

**Ngữ cảnh truy xuất (Contexts):**
- # Bị hen suyễn kèm trào ngược dạ dày thực quản phải làm sao?

Câu hỏi: Bị hen suyễn kèm trào ngược dạ dày thực quản phải...
- # Tôi bị bệnh hen suyễn, hiện đang phải uống thuốc (loại biệt dược, không phải kháng sinh) và huyết áp lần đo gần nhất l...
- hi lên cơn khó thở. Trường hợp này có cần phải tiêm vaccine ngừa không? Nếu tiêm ngừa thì nên sử dụng loại vaccine nào l...

**Đáp án chuẩn (Ground Truth):**
> Hen suyễn là bệnh viêm mãn tính đường hô hấp gây co thắt phế quản. Salbutamol là thuốc giãn phế quản tác dụng ngắn (SABA) dùng để cắt cơn hen cấp tính. Khi lên cơn, bệnh nhân xịt 1-2 nhát xịt hít định liều, có thể lặp lại sau vài phút nếu chưa đỡ.

**Hệ thống trả lời (Generated Answer):**
> **Hen suyễn là gì?**

Hen suyễn (hay còn gọi là bệnh hen suyễn) là một tình trạng sức khỏe khi phế quản không thể mở rộng để thở. Điều này dẫn đến khó thở, ho và các triệu chứng khác.

**Cách sử dụng Salbutamol khi lên cơn Hen Suyễn**

Salbutamol (hay còn gọi là Ventolin) là một loại thuốc hít được sử dụng để điều trị cơn hen suyễn. Dưới đây là cách sử dụng Salbutamol đúng cách:

1. **Sử dụng đúng liều lượng**: Liều lượng của Salbutamol thường là 2-4 puffs (hay còn gọi là 100-200 mcg) mỗi lần, với khoảng cách giữa các lần sử dụng là 4-6 giờ.
2. **Sử dụng đúng cách**: Khi sử dụng Salbutamol, hãy hít sâu và đều đặn qua mũi hoặc miệng, sau đó giữ hơi thở trong 10-15 giây trước khi thở ra.
3. **Không lạm dụng**: Không nên sử dụng Salbutamol quá nhiều lần trong ngày, vì điều này có thể dẫn đến tác dụng phụ như nhịp tim nhanh, run rẩy và lo lắng.
4. **Cần gặp bác sĩ nếu triệu chứng không cải thiện**: Nếu sau khi sử dụng Salbutamol mà triệu chứng hen suyễn không cải thiện hoặc trở nặng hơn, hãy gặp bác sĩ để được tư vấn và điều trị phù hợp.

**Lưu ý quan trọng**

* Không nên tự ý ngưng sử dụng thuốc hay thay đổi liều lượng mà không có sự giám sát của bác sĩ.
* Nếu bạn đang mang thai hoặc cho con bú, hãy tham khảo ý kiến của bác sĩ trước khi sử dụng Salbutamol.
* Nếu bạn có bất kỳ vấn đề sức khỏe nào khác, hãy thông báo cho bác sĩ biết để được tư vấn và điều trị phù hợp.

**Tham khảo chung**

Nếu bạn cần thêm thông tin hoặc có câu hỏi về cách sử dụng Salbutamol, hãy tham khảo ý kiến của bác sĩ hoặc chuyên gia y tế.

---

### Câu 7: sỏi thận có những triệu chứng gì nổi bật

**Chỉ số đo đạc:**
- Semantic Similarity: **0.7252**
- ROUGE-L: **0.1469**
- BLEU-4: **0.0183**

**Ngữ cảnh truy xuất (Contexts):**
- # Ưu điểm khi tán sỏi thận qua da bằng ống soi mềm là gì?

Câu hỏi: Ưu điểm khi tán sỏi thận qua da bằng ống soi mềm là ...
- # Tôi bị cao huyết áp, thiếu máu cơ tim cục bộ, sỏi thận đã mổ hai bên, viêm mũi dị ứng có nên tiêm vaccine Covid-19 khô...
- # Tiểu đêm, đau bụng dưới, đau bàng quang là triệu chứng của bệnh gì và điều trị như thế nào?

Câu hỏi: Tiểu đêm, đau bụ...

**Đáp án chuẩn (Ground Truth):**
> Triệu chứng nổi bật nhất của sỏi thận là cơn đau quặn thận (đau dữ dội vùng hố thắt lưng lan ra phía trước và xuống vùng bẹn sinh dục). Đi kèm có thể có tiểu buốt, tiểu rắt, tiểu ra máu, hoặc sốt, rét run nếu có nhiễm trùng đường tiết niệu.

**Hệ thống trả lời (Generated Answer):**
> **Sỏi thận có những triệu chứng gì nổi bật?**

Sỏi thận là một tình trạng bệnh lý khi các chất khoáng trong nước tiểu kết tinh và tạo thành sỏi. Các triệu chứng của sỏi thận thường bao gồm:

* Đau bụng hoặc đau lưng
* Tiêu chảy hoặc táo bón
* Sốt cao
* Tiểu khó hoặc tiểu ra máu
* Mất nước dẫn đến mệt mỏi

Lưu ý: Những triệu chứng này có thể không xuất hiện ngay lập tức và có thể thay đổi tùy thuộc vào kích thước và vị trí của sỏi.

**Tham khảo chung:** Nếu bạn nghi ngờ mình bị sỏi thận, hãy tham khảo ý kiến bác sĩ để được chẩn đoán và điều trị phù hợp.

---

### Câu 8: kháng sinh amoxicillin thường được chỉ định cho những trường hợp nào

**Chỉ số đo đạc:**
- Semantic Similarity: **0.7450**
- ROUGE-L: **0.1294**
- BLEU-4: **0.0099**

**Ngữ cảnh truy xuất (Contexts):**
- # Tôi bị dị ứng kháng sinh gốc Amo khi uống bia rượu là bị mẩn đỏ khắp người. Nhiều người bảo tôi bị di ứng cồn thì có t...
- uẩn, giảm đau viêm.Khi làm tất cả các biện pháp trên mà vẫn thấy đau viêm nhiều ảnh hưởng tới ăn, ngủ, sinh hoạt thì bạn...
- # Thuốc điều trị amidan có ảnh hưởng đến kết quả xét nghiệm HP không?

Câu hỏi: Thuốc điều trị amidan có ảnh hưởng đến k...

**Đáp án chuẩn (Ground Truth):**
> Amoxicillin là kháng sinh nhóm Penicillin phổ rộng, thường chỉ định cho các nhiễm khuẩn nhạy cảm như nhiễm trùng đường hô hấp trên (viêm tai giữa, viêm xoang, viêm họng), nhiễm trùng đường tiết niệu, nhiễm trùng da và mô mềm.

**Hệ thống trả lời (Generated Answer):**
> **Kháng sinh Amoxicillin thường được chỉ định cho những trường hợp nào?**

Theo các tài liệu y khoa, kháng sinh Amoxicillin thường được sử dụng để điều trị các bệnh nhiễm khuẩn như viêm họng, viêm phổi, viêm amidan, và một số bệnh lý khác. Tuy nhiên, cần lưu ý rằng việc sử dụng kháng sinh phải được chỉ định bởi bác sĩ và tuân theo hướng dẫn của họ.

Trong trường hợp bạn bị đau viêm nhiều ảnh hưởng tới ăn, ngủ, sinh hoạt, bác sĩ có thể cho bạn dùng thêm thuốc kháng sinh Amoxicillin để điều trị.

Ngoài ra, trong một số trường hợp khác như viêm amidan kèm theo do nhiễm khuẩn, bác sĩ cũng có thể chỉ định sử dụng kháng sinh Amoxicillin.

Lưu ý rằng việc sử dụng kháng sinh phải được thực hiện đúng cách và tuân theo hướng dẫn của bác sĩ để tránh các tác dụng phụ không mong muốn.

---

### Câu 9: các triệu chứng điển hình của covid 19 là gì

**Chỉ số đo đạc:**
- Semantic Similarity: **0.8328**
- ROUGE-L: **0.2162**
- BLEU-4: **0.0859**

**Ngữ cảnh truy xuất (Contexts):**
- ang ở giai đoạn bé được 8, 5 tháng, chưa phải đối tượng được nhà nước cho tiêm ngừa. Vì hiện tình hình vaccine vẫn còn đ...
- # Tôi bị viêm gan B có tiêm được vaccine Covid-19 không?

Câu hỏi: Tôi bị viêm gan B có tiêm được vaccine Covid-19 không...
- huộc nhóm chống chỉ định tiêm ngừa vaccine Covid-19. Còn nếu dị ứng mức độ nhẹ chỉ có biểu hiện ở da niêm như nổi mẩn mề...

**Đáp án chuẩn (Ground Truth):**
> Các triệu chứng điển hình của COVID-19 bao gồm sốt, ho khan, mệt mỏi, đau họng, mất vị giác hoặc khứu giác, đau nhức cơ thể, nhức đầu. Trường hợp nặng có thể xuất hiện khó thở và suy hô hấp.

**Hệ thống trả lời (Generated Answer):**
> **Triệu chứng điển hình của Covid-19**

Covid-19 là một bệnh nhiễm trùng do virus SARS-CoV-2 gây ra. Triệu chứng điển hình của Covid-19 bao gồm:

* Sốt cao (trên 38 độ C)
* Hắt hơi và ho
* Mệt mỏi, đau đầu, đau cơ
* Khó thở, khó chịu ở ngực
* Đau họng, đau cổ
* Mất vị giác hoặc khứu giác

Tuy nhiên, cần lưu ý rằng không phải tất cả mọi người đều có các triệu chứng này. Một số người có thể không có bất kỳ triệu chứng nào, còn một số người có thể có các triệu chứng nặng hơn.

**Tham khảo chung**

Nếu bạn nghi ngờ mình đã mắc Covid-19 hoặc có tiếp xúc với người nhiễm virus, hãy liên hệ ngay với cơ sở y tế gần nhất để được tư vấn và điều trị phù hợp.

---

### Câu 10: dấu hiệu nhồi máu cơ tim cấp và cách xử trí ban đầu

**Chỉ số đo đạc:**
- Semantic Similarity: **0.6025**
- ROUGE-L: **0.1128**
- BLEU-4: **0.0223**

**Ngữ cảnh truy xuất (Contexts):**
- # Sốt xuất huyết Dengue thì có nên điều trị tại nhà không?

Câu hỏi: Sốt xuất huyết Dengue thì có nên điều trị tại nhà k...
- # Nữ giới sốt, mẩn đỏ trên da là dấu hiệu bệnh gì?

Câu hỏi: Nữ giới sốt, mẩn đỏ trên da là dấu hiệu bệnh gì?

Trả lời: ...
- # Sốt xuất huyết uống thuốc 11 ngày không khỏi phải làm sao?

Câu hỏi: Sốt xuất huyết uống thuốc 11 ngày không khỏi phải...

**Đáp án chuẩn (Ground Truth):**
> Dấu hiệu điển hình của nhồi máu cơ tim là đau thắt ngực dữ dội (cảm giác đè nén, bóp nghẹt sau xương ức kéo dài trên 15 phút, lan lên vai, cằm hoặc tay trái). Xử trí ban đầu cần cho bệnh nhân nằm nghỉ ngay lập tức, gọi cấp cứu 115, và có thể cho nhai Aspirin nếu không có chống chỉ định.

**Hệ thống trả lời (Generated Answer):**
> **Dấu hiệu nhồi máu cơ tim cấp và cách xử trí ban đầu**

Nhồi máu cơ tim (NHMCT) là tình trạng khi một hoặc nhiều mạch máu trong tim bị tắc nghẽn, dẫn đến thiếu máu nuôi dưỡng cho các tế bào cơ tim. Dấu hiệu của NHMCT cấp có thể bao gồm:

* Sốt cao đột ngột
* Đau hốc mắt
* Đau cơ
* Đau bụng
* Mệt mỏi li bì
* Nôn nhiều
* Xuất huyết niêm mạc (chảy máu chân răng, chảy máu mũi,...)

Nếu bạn hoặc người thân có các dấu hiệu trên, cần được đưa đến bệnh viện ngay lập tức để được khám và điều trị kịp thời. Tình trạng thoát huyết tương có thể dẫn đến sốc, ứ dịch, suy hô hấp, xuất huyết nặng, suy tạng nặng và tử vong.

**Cách xử trí ban đầu**

Khi nghi ngờ NHMCT cấp, cần thực hiện các bước sau:

1. Gọi cấp cứu hoặc đưa người bệnh đến bệnh viện ngay lập tức.
2. Đảm bảo không gian thông thoáng để giúp người bệnh dễ thở.
3. Không cho người bệnh uống thuốc hoặc chất lỏng nào khác mà không có sự giám sát của bác sĩ.
4. Tránh di chuyển người bệnh quá nhiều, vì điều này có thể làm tăng nguy cơ xuất huyết và suy hô hấp.

Lưu ý: Những thông tin trên chỉ mang tính tham khảo chung và không thay thế cho lời khuyên y tế chuyên nghiệp. Nếu bạn hoặc người thân nghi ngờ bị NHMCT cấp, cần được khám và điều trị bởi bác sĩ chuyên khoa tim mạch.

---
