import 'package:flutter/material.dart';
import 'package:vize/vize.dart';
import '../../domain/survey.dart';
import 'colors.dart';

// Карточка с результатами всех вопросов опроса
class SurveyResultsCard extends StatelessWidget {
  final String date;
  final List<SurveyQuestionResult> questions;

  const SurveyResultsCard({
    super.key,
    required this.date,
    required this.questions,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: ps(v: 14.fh, h: 14.fw),
      decoration: BoxDecoration(
        color: white,
        borderRadius: BorderRadius.circular(12.r),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'РЕЗУЛЬТАТЫ ОПРОСА $date',
            style: TextStyle(
              fontFamily: 'SF Pro',
              fontSize: 15.fh,
              fontWeight: .w700,
              color: grey,
            ),
          ),
          SizedBox(height: 20.fh),

          ...questions.asMap().entries.map((entry) {
            final index = entry.key;
            final question = entry.value;

            return Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (index > 0) ...[
                  SizedBox(height: 7.fh),
                  Divider(color: text.withOpacity(0.2), height: 1),
                  SizedBox(height: 17.fh),
                ],
                Text(
                  question.title,
                  style: TextStyle(
                    fontFamily: 'SF Pro',
                    fontSize: 11.fh,
                    fontWeight: .w500,
                    color: black,
                  ),
                ),
                SizedBox(height: 12.fh),
                if (question.options.isEmpty)
                  Text(
                    'Нет ответов',
                    style: TextStyle(fontFamily: 'SF Pro', fontSize: 10.fh, color: grey),
                  )
                else
                  ...question.options.map(_buildProgressBar),
              ],
            );
          }),
        ],
      ),
    );
  }

  // Отрисовка полоски прогресса для одного варианта ответа
  Widget _buildProgressBar(SurveyResultItem item) {
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
                  child: LinearProgressIndicator(
                    value: item.percentage / 100,
                    minHeight: 9.fh,
                    backgroundColor: results,
                    valueColor: AlwaysStoppedAnimation<Color>(barColor),
                  ),
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