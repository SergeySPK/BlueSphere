import 'package:flutter/material.dart';
import 'package:vize/vize.dart';
import 'colors.dart';

// Модель для одного варианта ответа в опросе
class SurveyResultItem {
  final String label; // Текст варианта
  final int percentage; // Процент ответивших
  final bool isHighlighted; // Нужно ли подсветить этот вариант

  SurveyResultItem({required this.label, required this.percentage, this.isHighlighted = false});
}

// Виджет с результатами опроса
class SurveyResultsCard extends StatelessWidget {
  final String date; // Дата опроса
  final List<SurveyResultItem> generalResults; // Общая оценка состояния
  final List<SurveyResultItem> stressSubjects; // Самые тревожные предметы
  final List<SurveyResultItem> easySubjects; // Самые легкие предметы

  const SurveyResultsCard({super.key, required this.date, required this.generalResults, required this.stressSubjects, required this.easySubjects});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: ps(v: 14.fh, h: 14.fw),
      decoration: BoxDecoration(color: white, borderRadius: BorderRadius.circular(12.r)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'РЕЗУЛЬТАТЫ ОПРОСА $date',
            style: TextStyle(fontFamily: 'SF Pro', fontSize: 15.fh, fontWeight: .w700, color: grey),
          ),
          SizedBox(height: 20.fh),
          Text(
            'Общая оценка состояния после учебного дня',
            style: TextStyle(fontFamily: 'SF Pro', fontSize: 11.fh, fontWeight: .w500, color: black),
          ),
          SizedBox(height: 13.fh),
          ...generalResults.map((item) => _buildProgressBar(item)),

          SizedBox(height: 7.fh),
          Divider(color: text.withOpacity(0.2), height: 1),
          SizedBox(height: 17.fh),
          Text(
            'Предметы, на которых сегодня ученикам\nбыло больше всего тревожно',
            style: TextStyle(fontFamily: 'SF Pro', fontSize: 11.fh, fontWeight: .w500, color: black),
          ),
          SizedBox(height: 12.fh),
          ...stressSubjects.map((item) => _buildProgressBar(item)),

          SizedBox(height: 7.fh),
          Divider(color: text.withOpacity(0.2), height: 1),
          SizedBox(height: 17.fh),
          Text(
            'Предметы, на которых сегодня ученикам\nбыло легко',
            style: TextStyle(fontFamily: 'SF Pro', fontSize: 11.fh, fontWeight: .w500, color: black),
          ),
          SizedBox(height: 12.fh),
          ...easySubjects.map((item) => _buildProgressBar(item)),
        ],
      ),
    );
  }

  // Отрисовка одной полоски прогресса
  Widget _buildProgressBar(SurveyResultItem item) {
    // Выбираем цвет полоски в зависимости от процента
    Color getBarColor(int percent) {
      if (percent >= 70) return loadMax;
      if (percent >= 40) return loadHigh;
      if (percent >= 20) return loadMedium;
      if (percent >= 5) return loadLow;
      return loadMin;
    }

    final barColor = item.isHighlighted ? loadMax : getBarColor(item.percentage);

    return Padding(
      padding: po(b: 8.fh),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            item.label,
            style: TextStyle(fontFamily: 'SF Pro', fontSize: 10.fh, color: black, fontWeight: .w400),
          ),
          Row(
            children: [
              Expanded(
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(8),
                  child: LinearProgressIndicator(value: item.percentage / 100, minHeight: 9.fh, backgroundColor: results, valueColor: AlwaysStoppedAnimation<Color>(barColor)),
                ),
              ),
              SizedBox(width: 10.fw),
              SizedBox(
                width: 35.fw,
                child: Text(
                  '${item.percentage}%',
                  textAlign: TextAlign.right,
                  style: TextStyle(fontFamily: 'Inter', fontSize: 12.fh, color: black),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
