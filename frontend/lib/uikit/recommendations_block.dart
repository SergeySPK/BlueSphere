import 'package:flutter/material.dart';
import 'package:vize/vize.dart';
import 'colors.dart';

// Кастомный блок рекомендаций
class RecommendationsBlock extends StatelessWidget {
  final List<int> daysToReduce; // Уменьшить нагрузку
  final List<int> daysToMoveTo; // Можно поменять с днем

  const RecommendationsBlock({super.key, required this.daysToReduce, required this.daysToMoveTo});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: pa(16),
      decoration: BoxDecoration(color: white, borderRadius: BorderRadius.circular(12)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(
                'РЕКОМЕНДАЦИИ',
                style: TextStyle(fontFamily: 'SF Pro', fontSize: 15, fontWeight: .w700, color: classColor),
              ),
              SizedBox(width: 4.fw),
              Image.asset('assets/star.png', width: 13.fw, height: 13.fh, color: classColor),
            ],
          ),
          Text(
            'уменьшите нагрузку с',
            style: TextStyle(fontFamily: 'SF Pro', fontSize: 10, fontWeight: .w400, color: text),
          ),
          SizedBox(height: 4.fh),
          Wrap(
            spacing: 7.fw,
            runSpacing: 8.fh,
            children: daysToReduce.map((day) {
              return _buildDayChip(day, loadMax, white);
            }).toList(),
          ),
          SizedBox(height: 8.fh),
          Text(
            'между менее загруженными днями',
            style: TextStyle(fontFamily: 'SF Pro', fontSize: 10, fontWeight: .w400, color: text),
          ),
          SizedBox(height: 4.fh),
          Row(
            children: [
              Wrap(
                spacing: 7.fw,
                runSpacing: 8.fh,
                children: daysToMoveTo.map((day) {
                  return _buildDayChip(day, loadMin, white);
                }).toList(),
              ),
              Spacer(),
              Align(
                alignment: Alignment.centerRight,
                child: Text(
                  'составлено с помощью\nИИ-ассистента',
                  textAlign: TextAlign.right,
                  style: TextStyle(fontFamily: 'SF Pro', fontSize: 8, fontWeight: .w400, color: text),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildDayChip(int day, Color backgroundColor, Color textColor) {
    return Container(
      width: 30.fw,
      height: 30.fh,
      alignment: Alignment.center,
      decoration: BoxDecoration(color: backgroundColor, borderRadius: BorderRadius.circular(5)),
      child: Text(
        '$day',
        style: TextStyle(fontFamily: 'Inter', fontSize: 10, fontWeight: .w400, color: textColor),
      ),
    );
  }
}
