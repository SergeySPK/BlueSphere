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
  final String weekday;
  final List<LessonData> lessons;
  final Color statusColor;
  final Function(LessonData)? onEditLesson;
  final int? editingLessonNumber;

  const ScheduleCard({super.key, required this.day, required this.month, required this.weekday, required this.lessons, required this.statusColor, this.onEditLesson, this.editingLessonNumber});

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
                    weekday,
                    style: TextStyle(fontFamily: 'SF Pro', fontSize: 12, fontWeight: .w400, color: text),
                  ),
                ],
              ),
            ],
          ),
          SizedBox(height: 16.fh),
          if (lessons.isEmpty)
            Padding(
              padding: po(t: 16, b: 16),
              child: Center(
                child: Text(
                  'Нет уроков на этот день',
                  style: TextStyle(fontFamily: 'SF Pro', fontSize: 14, color: text),
                ),
              ),
            )
          else
            ...lessons.map((lesson) {
              final isEditing = lesson.number == editingLessonNumber;
              return Padding(
                padding: po(b: 16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Padding(
                          padding: po(t: 4),
                          child: Text(
                            '${lesson.number}. ',
                            style: TextStyle(fontFamily: 'Inter', fontSize: 14, fontWeight: .w500, color: Color(0xff7D7D7D)),
                          ),
                        ),
                        Expanded(
                          child: Container(
                            padding: po(t: 4, b: 4, l: 8, r: 8),
                            decoration: BoxDecoration(
                              color: isEditing ? loadHigh.withOpacity(0.15) : Colors.transparent,
                              border: isEditing
                                  ? Border(
                                      left: BorderSide(color: loadHigh, width: 2),
                                      right: BorderSide(color: loadHigh, width: 2),
                                    )
                                  : null,
                            ),
                            child: RichText(
                              text: TextSpan(
                                children: [
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
                        ),
                        SizedBox(width: 12.fw),
                        GestureDetector(
                          onTap: () {
                            if (onEditLesson != null) onEditLesson!(lesson);
                          },
                          child: Container(
                            width: 26,
                            height: 26,
                            decoration: BoxDecoration(color: loadMax, borderRadius: BorderRadius.circular(4)),
                            child: Icon(Icons.edit_outlined, color: Colors.white, size: 18),
                          ),
                        ),
                      ],
                    ),

                    if (isEditing)
                      Row(
                        children: [
                          Spacer(),
                          Padding(
                            padding: ps(h: 30),
                            child: Container(
                              decoration: BoxDecoration(color: loadHigh),
                              child: Text(
                                'Анастасия Алексеевна Иванова', // пока хардкод
                                style: TextStyle(fontFamily: 'SF Pro', fontSize: 8, fontWeight: .w400, color: white),
                              ),
                            ),
                          ),
                        ],
                      ),
                    Padding(
                      padding: po(t: 8),
                      child: Divider(color: text.withOpacity(0.3), height: 1),
                    ),
                  ],
                ),
              );
            }),
          SizedBox(height: 15.fh),
        ],
      ),
    );
  }
}
