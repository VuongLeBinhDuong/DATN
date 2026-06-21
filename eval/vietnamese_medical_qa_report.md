# Báo cáo Đánh giá RAG Cục bộ (Pipeline: AGENT)

**Tổng số câu hỏi kiểm thử:** 5
**Định dạng:** 100% Offline (Không phụ thuộc LLM ngoài)

## Chỉ số Trung bình (Aggregate Metrics)

| Chỉ số | Điểm số | Ý nghĩa đánh giá |
| :--- | :--- | :--- |
| **SBERT Similarity** | 0.6598 | Độ tương đồng ngữ nghĩa của câu trả lời sinh ra so với đáp án chuẩn |
| **ROUGE-L** | 0.1584 | Mức độ giữ chuỗi con chung dài nhất (đo độ phủ thông tin từ vựng) |
| **BLEU-4** | 0.0391 | Tỷ lệ trùng khớp các cụm từ (đo độ tự nhiên của câu chữ) |

## Chỉ số Tác tử (Agent Metrics)

| Chỉ số Tác tử | Điểm số / Thống kê | Ý nghĩa y khoa / kỹ thuật |
| :--- | :--- | :--- |
| **Số bước lập luận trung bình** | 2.00 | Số lần tác tử gọi công cụ tra cứu trước khi kết luận |
| **Tỷ lệ Agent thành công** | 100.0% | Tỷ lệ Agent kết luận thành công không bị lỗi cú pháp |
| **Tổng số lỗi Parse định dạng** | 0 | Số lần mô hình sinh sai cú pháp `Thought/Action` |
| **Số lần kích hoạt Loop Guard** | 0 | Số lần chặn vòng lặp vô hạn (lặp câu hỏi tra cứu) |

## Chi tiết từng câu hỏi (Detailed Results)

### Câu 1: Chào bác sĩ,
Răng cháu hiện tại có mủ ở dưới lợi nhưng khi đau cháu sẽ không ngủ được (quá đau). Tuy nhiên chỉ vài ngày là hết mà thỉnh thoảng nó lại bị đau. Chị cháu bảo là trước chị cháu cũng bị như vậy chỉ là đau răng tuổi dậy thì thôi. Bác sĩ cho cháu hỏi đau răng kèm có mủ dưới lợi là bệnh gì? Cháu có cần đi chữa trị không? Cháu cảm ơn.

**Chỉ số đo đạc:**
- Semantic Similarity: **0.7809**
- ROUGE-L: **0.1532**
- BLEU-4: **0.0106**
- Số bước lập luận: **2**
- Trạng thái Parse thành công: **True**
- Bị Loop Guard chặn: **False**

**Ngữ cảnh truy xuất (Contexts):**
- # Răng có lỗ chấm đen, chảy máu khi thức dậy là sao?

Câu hỏi: Răng có lỗ chấm đen, chảy máu khi thức dậy là sao?

Trả l...
- # Đau răng khi mang thai phải làm sao?

Câu hỏi: Đau răng khi mang thai phải làm sao?

Trả lời: Theo như thông tin của b...
- # Nổi hạch vì viêm lợi để lâu có ảnh hưởng gì không?

Câu hỏi: Nổi hạch vì viêm lợi để lâu có ảnh hưởng gì không?

Trả l...

**Đáp án chuẩn (Ground Truth):**
> Chào bạn,
Để trả lời câu hỏi trên, bác sĩ xin giải đáp như sau:
Răng bạn hiện tại có mủ dưới lợi gây đau nhức nhiều. Bạn có thể đến phòng khám răng hàm mặt bệnh viện để được thăm khám, chụp phim và tư vấn cho bạn được chính xác
Trân trọng!

**Hệ thống trả lời (Generated Answer):**
> Bạn đang gặp phải tình trạng đau răng và mủ dưới lợi, đây là một dấu hiệu của bệnh gì? Có thể bạn đang mắc phải bệnh tê bì nửa mặt hoặc Viêm nướu. Để được chẩn đoán và điều trị chính xác, bạn cần đi khám bác sĩ chuyên khoa Răng - Hàm - Mặt.

Nếu được chẩn đoán mắc phải bệnh tê bì nửa mặt hoặc Viêm nướu, thì có thể sẽ cần phải điều trị bằng thuốc kháng sinh hoặc phẫu thuật. Tuy nhiên, trước khi đi khám bác sĩ, bạn nên tìm hiểu thêm về các thông tin sau:

* Các triệu chứng đau răng và mủ dưới lợi có thể là dấu hiệu của nhiều bệnh khác nhau.
* Bạn cần phải đi khám bác sĩ chuyên khoa Răng - Hàm - Mặt để được chẩn đoán và điều trị chính xác.

Hy vọng những thông tin trên sẽ giúp bạn hiểu rõ hơn về tình trạng đau răng và mủ dưới lợi tuổi dậy thì.

---
Nguồn trả lời: RAG (GraphRAG + LLM tổng hợp)

---

### Câu 2: Chào bác sĩ,
Em thấy mặt dưới, phía cuống lưỡi của mình có 2 nốt mụn nhỏ, đỏ xung quanh, ở giữa có nhân trắng, đau nhẹ khi dùng đầu lưỡi chạm vào. Đồng thời, phía cuống lưỡi mặt trên cũng có các nốt lớn nổi lên, không gây đau. Bác sĩ cho em hỏi cuống lưỡi nổi mụn nhỏ là dấu hiệu bệnh gì? Có phải em đang mắc bệnh gì không hay chỉ bị nhiệt miệng bình thường? Em cảm ơn bác sĩ.

**Chỉ số đo đạc:**
- Semantic Similarity: **0.7117**
- ROUGE-L: **0.0957**
- BLEU-4: **0.0133**
- Số bước lập luận: **2**
- Trạng thái Parse thành công: **True**
- Bị Loop Guard chặn: **False**

**Ngữ cảnh truy xuất (Contexts):**
- đường tiết niệu, hãy để ý đến các triệu chứng sau:Cảm giác rát buốt khi bạn đi tiểu.Đi tiểu thường xuyên, thậm chí khi b...
- g ngáy. Trong hầu hết các trường hợp gây cản trở, khiến cho không khí giữa thanh quản và mũi lưu thông không được bình t...
- tai.Phần lớn, tình trạng phát ban sẽ biến mất sau một thời gian ngắn, trong khi chờ phát ban da biến mất, bạn có thể thự...

**Đáp án chuẩn (Ground Truth):**
> Chào bạn,
Để trả lời câu hỏi trên, bác sĩ xin giải đáp như sau:
Triệu chứng nốt mụn đỏ vùng dưới lưỡi, đau khi chạm vào gợi ý tình trạng mụn viêm vùng lưỡi, nếu nốt mụn không to thêm và tự hết trong 7-10 ngày thì bạn không cần quá lo lắng.
Trong trường hợp nốt mụn to dần hoặc nốt mụn tồn tại trên 02 tuần không hết thì bạn cần đến bác sĩ để khám kiểm tra. Đối với các nốt lớn mặt trên lưỡi thì bạn có thể đến phòng khám Tai mũi họng để bác sĩ khám kiểm tra và tư vấn cụ thể hơn.
Trân trọng!

**Hệ thống trả lời (Generated Answer):**
> Bạn nên đến phòng khám Răng - Hàm - Mặt để được khám và chẩn đoán bị nổi mụn bên dưới lưỡi là bệnh gì. Nếu không đau rát có thể do nghẽn tạm thời tuyến nước bọt lạc chỗ.

Lưu ý: Nổi mụn dưới lưỡi cũng có thể do các nguyên nhân khác như viêm Lympho thành sau họng, sưng lưỡi, phát ban da,...

---
Nguồn trả lời: RAG (GraphRAG + LLM tổng hợp)

---

### Câu 3: Chào bác sĩ,
Từ tháng 4/2020, em mới xuất hiện lần đầu triệu chứng viêm amidan có mủ và sốt. Tuy nhiên, kể từ thời gian đó trở đi, bệnh tái phát nhiều lần (khoảng 1,2 tháng bị 01 lần), nhất là sau khi bị cảm tình trạng viêm nặng hơn lúc bình thường (sốt và có mủ, không tự khỏi được). Tình trạng trên ảnh hưởng rất nhiều đến sức khỏe và sinh hoạt của bản thân. Bác sĩ cho em hỏi viêm amidan có mủ kèm sốt tái phát nhiều lần phải làm sao? Em có nguy cơ bị ung thư vòm họng không? Em cảm ơn.

**Chỉ số đo đạc:**
- Semantic Similarity: **0.5802**
- ROUGE-L: **0.1472**
- BLEU-4: **0.0456**
- Số bước lập luận: **2**
- Trạng thái Parse thành công: **True**
- Bị Loop Guard chặn: **False**

**Ngữ cảnh truy xuất (Contexts):**
- # Viêm amidan tái lại nên làm gì? Bệnh trào ngược dạ dày có liên quan viêm họng không?

Câu hỏi: Viêm amidan tái lại nên...
- # Đi ngoài nhiều lần và hơi ê bụng là dấu hiệu của bệnh gì?

Câu hỏi: Đi ngoài nhiều lần và hơi ê bụng là dấu hiệu của b...
- # Đau đầu khó chịu đã uống thuốc nhưng không đỡ phải làm thế nào?

Câu hỏi: Đau đầu khó chịu đã uống thuốc nhưng không đ...

**Đáp án chuẩn (Ground Truth):**
> Chào bạn,
Để trả lời câu hỏi trên, bác sĩ xin giải đáp như sau:
Các triệu chứng sốt, đau họng, amidan có mủ tái đi tái lại nhiều lần gợi ý tình trạng viêm amidan mạn. Tình trạng viêm amidan của chị tái đi tái lại thường xuyên, ảnh hưởng nhiều đến sức khỏe và sinh hoạt bản thân do đó có chỉ định cắt amidan để điều trị hiệu quả tình trạng trên.
Viêm amidan mạn không phải là nguy cơ ung thư vòm họng, tuy vậy bạn nên đến phòng khám Tai mũi họng để khám, nội soi kiểm tra nhằm xác định có đúng là chị đang có tình trạng viêm amidan mạn hay không, đồng thời tầm soát thêm một số nguyên nhân gây sốt, đau họng khác.
Trân trọng!

**Hệ thống trả lời (Generated Answer):**
> Viêm amidan tái phát có thể do nhiều nguyên nhân khác nhau, bao gồm vi khuẩn hoặc virus gây ra, thói quen ăn uống không lành mạnh, chế độ sinh hoạt không phù hợp và tình trạng sức khỏe tổng thể. Để điều trị viêm amidan tái phát, bạn có thể tham khảo các biện pháp sau:

* Uống thuốc kháng sinh hoặc thuốc chống virus theo chỉ định của bác sĩ
* Thay đổi chế độ ăn uống và sinh hoạt để giảm thiểu tình trạng viêm amidan
* Tránh tiếp xúc với môi trường có nhiều vi khuẩn hoặc virus

Lưu ý: Trước khi thực hiện bất kỳ biện pháp điều trị nào, bạn nên tham khảo ý kiến của bác sĩ để đảm bảo an toàn và hiệu quả.

Người dùng cũng có thể tham khảo các tài liệu về viêm amidan và cách điều trị tại các nguồn uy tín.

---
Nguồn trả lời: RAG (GraphRAG + LLM tổng hợp)

---

### Câu 4: Chào bác sĩ,
Dạo gần đây, mỗi tối ngủ con hay bị nghẹt mũi kèm theo vướng họng nhưng không có đờm, đặc biệt là lúc nằm xuống. Còn ban ngày chỉ thấy vướng họng. Bác sĩ cho con hỏi nghẹt mũi kèm vướng họng là dấu hiệu bệnh gì? Con cảm ơn.

**Chỉ số đo đạc:**
- Semantic Similarity: **0.8084**
- ROUGE-L: **0.2482**
- BLEU-4: **0.0693**
- Số bước lập luận: **2**
- Trạng thái Parse thành công: **True**
- Bị Loop Guard chặn: **False**

**Ngữ cảnh truy xuất (Contexts):**
- # Thường xuyên nghẹt mũi buổi tối có phải do khối nang vòm mũi không và điều trị thế nào?

Câu hỏi: Thường xuyên nghẹt m...
- u không khí trong phòng bị khô quá có thể sử dụng các máy tạo ẩm và vòi phun sương ở đầu giường để tăng độ ẩm trong phòn...
- # Đờm vướng ở cổ họng, ho nhiều, nghẹt mũi là bị làm sao?

Câu hỏi: Đờm vướng ở cổ họng, ho nhiều, nghẹt mũi là bị làm s...

**Đáp án chuẩn (Ground Truth):**
> Chào bạn,
Để trả lời câu hỏi trên, bác sĩ xin giải đáp như sau:
Các dấu hiệu: nghẹt mũi, vướng họng có thể gặp trong các bệnh lý viêm mũi xoang, viêm họng, viêm amidan, trào ngược dạ dày - thực quản,... Bạn có thể đến phòng khám Tai mũi họng để nội soi mũi xoang, họng - thanh quản kiểm tra và tư vấn điều trị hiệu quả.
Trân trọng!

**Hệ thống trả lời (Generated Answer):**
> Nghẹt mũi kèm vương họng có thể là dấu hiệu của nhiều bệnh lý khác nhau, bao gồm hội chứng Covid-19 kéo dài, viêm xoang hoặc viêm vòm. Để xác định chính xác nguyên nhân, bạn nên đi khám bác sĩ chuyên khoa tai mũi họng để được chẩn đoán và điều trị phù hợp.

---
Nguồn trả lời: RAG (GraphRAG + LLM tổng hợp)

---

### Câu 5: Chào bác sĩ,
Em bị tăng tiết mồ hôi, nhất là vùng mặt và ngực ra rất nhiều. Bác sĩ cho em hỏi tăng tiết mồ hôi ở vùng mặt và ngực có điều trị được không? Em cảm ơn bác sĩ.

**Chỉ số đo đạc:**
- Semantic Similarity: **0.4181**
- ROUGE-L: **0.1478**
- BLEU-4: **0.0568**
- Số bước lập luận: **2**
- Trạng thái Parse thành công: **True**
- Bị Loop Guard chặn: **False**

**Ngữ cảnh truy xuất (Contexts):**
- # Vùng bụng và lưng ra nhiều mồ hôi sau mổ điều trị mồ hôi tay chân phải làm sao?

Câu hỏi: Vùng bụng và lưng ra nhiều m...
- ết mồ hôi) ngay cả khi nghỉ ngơi hay làm việc ít, tay chân luôn ẩm ướt, có khi nhỏ thành giọt gây bất tiện trong giao ti...
- # Sau mổ cắt hạch giao cảm có hết mồ hôi mặt và nách không?

Câu hỏi: Sau mổ cắt hạch giao cảm có hết mồ hôi mặt và nách...

**Đáp án chuẩn (Ground Truth):**
> Chào bạn,
Để trả lời câu hỏi trên, bác sĩ xin giải đáp như sau:
Tăng tiết mồ hôi nguyên phát thường do rối loạn chức năng của hệ thống thần kinh thực vật (cường giao cảm) gây nên; Yếu tố tinh thần, cảm xúc (lo âu, căng thẳng), sử dụng rượu bia, cà phê, thiếu ngủ là những tác nhân kích hoạt tuyến mồ hôi hoạt động mạnh hơn.
Tăng tiết mồ hôi thứ phát xảy ra sau khi mắc một số bệnh lý như đái tháo đường, cường giáp, bệnh gút, ung thư, nhiễm trùng, béo phì hoặc phụ nữ trong thời kỳ mãn kinh; tùy từng người, có biểu hiện tăng tiết mồ hôi vị trí khác nhau (nách, bàn tay, ngực...).
Bạn có thể điều trị bằng thuốc hoặc phẫu thuật; bạn nên đến bệnh viện khám chuyên khoa nội, ngoại lồng ngực để xác định nguyên nhân và tìm phương thức điều trị phù hợp.
Trân trọng!

**Hệ thống trả lời (Generated Answer):**
> **Tăng tiết mồ hôi vùng mặt và ngực có điều trị được không?**

Có, tăng tiết mồ hôi vùng mặt và ngực có nhiều phương pháp điều trị khác nhau. Một số phương pháp phổ biến bao gồm ion liệu pháp, tiêm Botulinum toxin A, phẫu thuật nội soi giao cảm và cắt bỏ hạch giao cảm ngực.

**Ion liệu pháp**: Đây là một phương pháp sử dụng ion để điều trị tăng tiết mồ hôi. Ion liệu pháp có thể giúp giảm tiết mồ hôi trong vòng 4-6 giờ sau khi uống thuốc.

**Tiêm Botulinum toxin A**: Phương pháp này sử dụng tiêm độc chất botulinum vào trong da để ngăn cản phóng thích chất acetylcholine tại khu vực tăng tiết mồ hôi.

**Phẫu thuật nội soi giao cảm**: Đây là một phương pháp phẫu thuật nội soi được áp dụng cho chứng tăng tiết mồ hôi tay, đối với mồ hôi và mùi ở nách có các chỉ định: Cắt bỏ tuyến mồ hôi nách, hút tuyến mồ hôi nách, hoặc tiêm Botox ức chế tiết mồ hôi nách.

**Cắt bỏ hạch giao cảm ngực**: Đây là một phương pháp phẫu thuật được áp dụng để điều trị tăng tiết mồ hôi bàn tay.

Tùy thuộc vào mức độ tăng tiết mồ hôi và tình trạng sức khỏe của bệnh nhân, bác sĩ sẽ lựa chọn phương pháp điều trị phù hợp.

---
Nguồn trả lời: RAG (GraphRAG + LLM tổng hợp)

---
