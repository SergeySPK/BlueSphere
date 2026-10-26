import 'package:flutter/material.dart';
import 'package:vize/vize.dart';
import 'colors.dart';

class LessonData {
  final int number;
  final String subject;
  final String type;

  LessonData({required this.number, required this.subject, required this.type});
}

class ScheduleCard extends StatelessWidget {
  final String day;
  final String month;
  final List<LessonData> lessons;
  final Color statusColor;
  final Function(LessonData)? onEditLesson;

  const ScheduleCard({super.key, required this.day, required this.month, required this.lessons, required this.statusColor, this.onEditLesson});

  // Функция для получения названия дня недели
  String _getWeekdayName(int dayNumber) {
    final now = DateTime.now();
    final months = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'];
    int monthNumber = months.indexWhere((m) => m.toLowerCase() == month.toLowerCase()) + 1;
    if (monthNumber == 0) monthNumber = now.month;
    final date = DateTime(now.year, monthNumber, dayNumber);
    final weekdays = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье'];
    return weekdays[date.weekday - 1];
  }

  @override
  Widget build(BuildContext context) {
    final weekdayName = _getWeekdayName(int.parse(day));

    return Container(
      padding: pa(16),
      decoration: BoxDecoration(color: white, borderRadius: BorderRadius.circular(12)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 32,
                height: 32,
                decoration: BoxDecoration(color: statusColor, borderRadius: BorderRadius.circular(8)),
                child: Center(
                  child: Text(
                    day,
                    style: TextStyle(fontFamily: 'Inter', fontSize: 14, fontWeight: .w700, color: white),
                  ),
                ),
              ),
              SizedBox(width: 12.fw),
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    month.toUpperCase(),
                    style: TextStyle(fontFamily: 'SF Pro', fontSize: 15, fontWeight: .w700, color: statusColor),
                  ),
                  Text(
                    weekdayName,
                    style: TextStyle(fontFamily: 'SF Pro', fontSize: 12, fontWeight: .w400, color: text),
                  ),
                ],
              ),
            ],
          ),
          SizedBox(height: 16.fh),
          ...lessons.map((lesson) {
            return Container(
              decoration: BoxDecoration(
                border: Border(bottom: BorderSide(color: statusColor.withOpacity(0.5), width: 1)),
              ),
              padding: po(t: 12, b: 12),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: RichText(
                      text: TextSpan(
                        children: [
                          TextSpan(
                            text: '${lesson.number}. ',
                            style: TextStyle(fontFamily: 'Inter', fontSize: 14, fontWeight: .w500, color: black),
                          ),
                          TextSpan(
                            text: '${lesson.subject}. ',
                            style: TextStyle(fontFamily: 'Inter', fontSize: 14, fontWeight: .w400, color: black),
                          ),
                          TextSpan(
                            text: lesson.type,
                            style: TextStyle(fontFamily: 'SF Pro', fontSize: 14, fontWeight: .w400, color: black),
                          ),
                        ],
                      ),
                    ),
                  ),
                  SizedBox(width: 12.fw),
                  GestureDetector(
                    onTap: () {
                      if (onEditLesson != null) onEditLesson!(lesson);
                    },
                    child: Container(
                      width: 26,
                      height: 26,
                      decoration: BoxDecoration(color: statusColor, borderRadius: BorderRadius.circular(4)),
                      child: Icon(Icons.edit_outlined, color: Colors.white, size: 18),
                    ),
                  ),
                ],
              ),
            );
          }),
          SizedBox(height: 8.fh),
          Center(
            child: Text(
              '${lessons.length} уроков: ${lessons.where((l) => l.type != 'Обычный урок').length} работы',
              style: TextStyle(fontFamily: 'SF Pro', fontSize: 12, fontWeight: .w400, color: text),
            ),
          ),
        ],
      ),
    );
  }
}
