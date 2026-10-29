import 'package:flutter/material.dart';
import 'package:vize/vize.dart';
import 'colors.dart';

class ClassSummaryCard extends StatelessWidget {
  // мок данные
  final String date;
  final int percentage;
  final String statusText;
  final String hardestSubject;
  final String easiestSubject;

  const ClassSummaryCard({super.key, required this.date, required this.percentage, required this.statusText, required this.hardestSubject, required this.easiestSubject});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: pa(14),
      decoration: BoxDecoration(color: white, borderRadius: BorderRadius.circular(12)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'ОБЩАЯ СВОДКА',
            style: TextStyle(fontFamily: 'SF Pro', fontSize: 15, fontWeight: .w700, color: black),
          ),
          SizedBox(height: 12.fh),
          Row(
            children: [
              Container(
                width: 79,
                height: 79,
                decoration: BoxDecoration(color: loadMax, shape: BoxShape.circle),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Text(
                      '$percentage',
                      style: TextStyle(fontFamily: 'SF Pro', fontSize: 30, fontWeight: .w800, color: white),
                    ),
                    Text(
                      '%',
                      style: TextStyle(fontFamily: 'SF Pro', fontSize: 11, fontWeight: .w800, color: white),
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
                      style: TextStyle(fontFamily: 'SF Pro', fontSize: 10, color: grey, fontWeight: .w400, letterSpacing: 2.88),
                    ),
                    SizedBox(height: 5.fh),
                    Text(
                      statusText,
                      style: TextStyle(fontFamily: 'Inter', fontSize: 14, fontWeight: .w700, color: loadMax),
                    ),
                    SizedBox(height: 2.fh),
                    Text(
                      'после сегодняшнего учебного дня',
                      style: TextStyle(fontFamily: 'SF Pro', fontSize: 10, color: grey, fontWeight: .w400, letterSpacing: 1.6),
                    ),
                  ],
                ),
              ),
            ],
          ),
          SizedBox(height: 20.fh),
          Column(
            children: [
              Container(
                padding: pa(8),
                decoration: BoxDecoration(color: background, borderRadius: BorderRadius.circular(8)),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Expanded(
                      child: Text(
                        'Самый тревожный урок\nна сегодня:',
                        style: TextStyle(fontFamily: 'SF Pro', fontSize: 10, color: grey, fontWeight: .w500),
                      ),
                    ),
                    Text(
                      hardestSubject,
                      style: TextStyle(fontFamily: 'SF Pro', fontSize: 18, fontWeight: .w600, color: loadMax),
                    ),
                  ],
                ),
              ),
              SizedBox(height: 8.fh),
              Container(
                padding: pa(8),
                decoration: BoxDecoration(color: background, borderRadius: BorderRadius.circular(8)),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Expanded(
                      child: Text(
                        'Самый легкий урок\nна сегодня:',
                        style: TextStyle(fontFamily: 'SF Pro', fontSize: 10, color: grey, fontWeight: .w500),
                      ),
                    ),
                    Text(
                      easiestSubject,
                      style: TextStyle(fontFamily: 'SF Pro', fontSize: 18, fontWeight: .w600, color: loadMax),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
