import 'package:flutter/material.dart';
import 'package:vize/vize.dart';
import '../../domain/survey.dart';
import 'colors.dart';

// Карточка с общей сводкой состояния класса
class ClassSummaryCard extends StatelessWidget {
  final String date;
  final int percentage;
  final String statusText;
  final List<SurveyQuestionSummary> questionSummaries;

  const ClassSummaryCard({
    super.key,
    required this.date,
    required this.percentage,
    required this.statusText,
    required this.questionSummaries,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: ps(v: 14.fh, h: 14.fw),
      decoration: BoxDecoration(color: white, borderRadius: BorderRadius.circular(12.r)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'ОБЩАЯ СВОДКА',
            style: TextStyle(fontFamily: 'SF Pro', fontSize: 15.fh, fontWeight: .w700, color: black),
          ),
          SizedBox(height: 12.fh),
          Row(
            children: [
              Container(
                width: 79.fw,
                height: 79.fh,
                decoration: BoxDecoration(color: loadMax, shape: BoxShape.circle),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Text(
                      '$percentage',
                      style: TextStyle(fontFamily: 'SF Pro', fontSize: 30.fh, fontWeight: .w800, color: white),
                    ),
                    Text(
                      '%',
                      style: TextStyle(fontFamily: 'SF Pro', fontSize: 11.fh, fontWeight: .w800, color: white),
                    ),
                  ],
                ),
              ),
              SizedBox(width: 11.fw),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'обучающихся чувствуют себя',
                      style: TextStyle(fontFamily: 'SF Pro', fontSize: 10.fh, color: grey, fontWeight: .w400, letterSpacing: 2.88),
                    ),
                    SizedBox(height: 5.fh),
                    Text(
                      statusText,
                      style: TextStyle(fontFamily: 'Inter', fontSize: 16.fh, fontWeight: .w700, color: loadMax),
                    ),
                    SizedBox(height: 2.fh),
                    Text(
                      'после сегодняшнего учебного дня',
                      style: TextStyle(fontFamily: 'SF Pro', fontSize: 10.fh, color: grey, fontWeight: .w400, letterSpacing: 1.6),
                    ),
                  ],
                ),
              ),
            ],
          ),
          SizedBox(height: 12.fh),
          Column(
            children: questionSummaries.map((summary) {
              return Padding(
                padding: po(b: 8.fh),
                child: Container(
                  padding: ps(h: 8.fw, v: 8.fh),
                  decoration: BoxDecoration(color: background, borderRadius: BorderRadius.circular(8.r)),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Expanded(
                        child: Text(
                          summary.title,
                          style: TextStyle(fontFamily: 'SF Pro', fontSize: 10.fh, color: grey, fontWeight: .w500),
                        ),
                      ),
                      SizedBox(width: 8.fw),
                      Flexible(
                        child: Text(
                          summary.topAnswer,
                          textAlign: TextAlign.right,
                          style: TextStyle(fontFamily: 'SF Pro', fontSize: 15.fh, fontWeight: .w600, color: loadMax),
                        ),
                      ),
                    ],
                  ),
                ),
              );
            }).toList(),
          ),
        ],
      ),
    );
  }
}