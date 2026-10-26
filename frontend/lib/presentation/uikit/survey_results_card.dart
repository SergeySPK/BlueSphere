import 'package:flutter/material.dart';
import 'package:vize/vize.dart';
import 'colors.dart';

class SurveyResultItem {
  final String label;
  final int percentage;
  final bool isHighlighted;

  SurveyResultItem({required this.label, required this.percentage, this.isHighlighted = false});
}

class SurveyResultsCard extends StatelessWidget {
  final String date;
  final List<SurveyResultItem> generalResults;
  final List<SurveyResultItem> stressSubjects;
  final List<SurveyResultItem> easySubjects;

  const SurveyResultsCard({super.key, required this.date, required this.generalResults, required this.stressSubjects, required this.easySubjects});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: pa(14),
      decoration: BoxDecoration(color: white, borderRadius: BorderRadius.circular(12)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'РЕЗУЛЬТАТЫ ОПРОСА $date',
            style: TextStyle(fontFamily: 'SF Pro', fontSize: 15, fontWeight: .w700, color: black),
          ),
          SizedBox(height: 11.fh),
          Text(
            'Общая оценка состояния после учебного дня',
            style: TextStyle(fontFamily: 'SF Pro', fontSize: 10, fontWeight: .w400, color: black),
          ),
          SizedBox(height: 17.fh),
          ...generalResults.map((item) => _buildProgressBar(item)),
          SizedBox(height: 7.fh),
          Divider(color: text.withOpacity(0.2), height: 1),
          SizedBox(height: 17.fh),
          Text(
            'Предметы, на которых сегодня ученикам\nбыло больше всего тревожно',
            style: TextStyle(fontFamily: 'SF Pro', fontSize: 10, fontWeight: .w400, color: black),
          ),
          SizedBox(height: 11.fh),
          ...stressSubjects.map((item) => _buildProgressBar(item)),
          SizedBox(height: 7.fh),
          Divider(color: text.withOpacity(0.2), height: 1),
          SizedBox(height: 17.fh),
          Text(
            'Предметы, на которых сегодня ученикам\nбыло легко',
            style: TextStyle(fontFamily: 'SF Pro', fontSize: 10, fontWeight: .w400, color: black),
          ),
          SizedBox(height: 11.fh),
          ...easySubjects.map((item) => _buildProgressBar(item)),
        ],
      ),
    );
  }

  Widget _buildProgressBar(SurveyResultItem item) {
    Color getBarColor(int percent) {
      if (percent >= 70) return loadMax; // 80-100%
      if (percent >= 40) return loadHigh; // 50-79%
      if (percent >= 20) return loadMedium; // 20-49%
      if (percent >= 5) return loadLow; // 5-19%
      return loadMin; // 0-4%
    }

    final barColor = item.isHighlighted ? loadMax : getBarColor(item.percentage);

    return Padding(
      padding: po(b: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            item.label,
            style: TextStyle(fontFamily: 'SF Pro', fontSize: 10, color: black, fontWeight: .w400),
          ),
          SizedBox(height: 5.fh),
          Row(
            children: [
              Expanded(
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(8),
                  child: LinearProgressIndicator(
                    value: item.percentage / 100,
                    minHeight: 12,
                    backgroundColor: results, // Серый фон
                    valueColor: AlwaysStoppedAnimation<Color>(barColor),
                  ),
                ),
              ),
              SizedBox(width: 12.fw),
              SizedBox(
                width: 35.fw,
                child: Text(
                  '${item.percentage}%',
                  textAlign: TextAlign.right,
                  style: TextStyle(fontFamily: 'Inter', fontSize: 12, color: black),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
