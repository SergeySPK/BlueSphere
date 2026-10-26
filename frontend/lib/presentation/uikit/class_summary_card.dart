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
                      'учащихся чувствуют себя',
                      style: TextStyle(fontFamily: 'SF Pro', fontSize: 10, color: bottomBarText, fontWeight: .w500),
                    ),
                    SizedBox(height: 5.fh),
                    Text(
                      statusText,
                      style: TextStyle(fontFamily: 'Inter', fontSize: 14, fontWeight: .w700, color: loadMax),
                    ),
                    SizedBox(height: 5.fh),
                    Text(
                      'по окончании сегодняшних уроков',
                      style: TextStyle(fontFamily: 'SF Pro', fontSize: 10, color: bottomBarText, fontWeight: .w500),
                    ),
                  ],
                ),
              ),
            ],
          ),
          SizedBox(height: 20.fh),
          Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Самый тревожный урок\nна сегодня:',
                      style: TextStyle(fontFamily: 'SF Pro', fontSize: 10, color: black),
                    ),
                    SizedBox(height: 16.fh),
                    Text(
                      'Самый легкий урок\nна сегодня:',
                      style: TextStyle(fontFamily: 'SF Pro', fontSize: 10, color: black),
                    ),
                  ],
                ),
              ),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Container(
                      padding: ps(v: 6),
                      width: 171.fw,
                      decoration: BoxDecoration(color: loadMax, borderRadius: BorderRadius.circular(8)),
                      child: Center(
                        child: Text(
                          hardestSubject,
                          style: TextStyle(fontFamily: 'SF Pro', fontSize: 12, fontWeight: .w500, color: white),
                        ),
                      ),
                    ),
                    SizedBox(height: 11.fh),
                    Container(
                      padding: ps(v: 6),
                      width: 171.fw,
                      decoration: BoxDecoration(color: loadMax, borderRadius: BorderRadius.circular(8)),
                      child: Center(
                        child: Text(
                          easiestSubject,
                          style: TextStyle(fontFamily: 'SF Pro', fontSize: 12, fontWeight: .w500, color: white),
                        ),
                      ),
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
