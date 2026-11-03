import 'package:flutter/material.dart';
import 'package:vize/vize.dart';
import 'colors.dart';

// Кастомный блок с расписанием
class LessonData {
  final int number;
  final String subject;
  final String type;
  final String teacherName;

  LessonData({required this.number, required this.subject, required this.type, required this.teacherName});
}

class ScheduleCard extends StatelessWidget {
  final String day;
  final String month;
  final String weekday;
  final List<LessonData> lessons;
  final Color statusColor;
  final Function(LessonData)? onEditLesson;
  final int? editingLessonNumber;
  final Color editingColor;

  const ScheduleCard({super.key, required this.day, required this.month, required this.weekday, required this.lessons, required this.statusColor, this.onEditLesson, this.editingLessonNumber, required this.editingColor});

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
                width: 40.fw,
                height: 40.fh,
                decoration: BoxDecoration(color: statusColor, borderRadius: BorderRadius.circular(5.r)),
                child: Center(
                  child: Text(
                    day,
                    style: TextStyle(fontFamily: 'Inter', fontSize: 12.fh, fontWeight: .w400, color: white),
                  ),
                ),
              ),
              SizedBox(width: 12.fw),
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    month.toUpperCase(),
                    style: TextStyle(fontFamily: 'SF Pro', fontSize: 24.fh, fontWeight: .w700, color: statusColor),
                  ),
                  Text(
                    weekday,
                    style: TextStyle(fontFamily: 'SF Pro', fontSize: 15.fh, fontWeight: .w400, color: text),
                  ),
                ],
              ),
            ],
          ),
          SizedBox(height: 16.fh),
          if (lessons.isEmpty)
            Padding(
              padding: ps(v: 16.fh),
              child: Center(
                child: Text(
                  'Нет уроков на этот день',
                  style: TextStyle(fontFamily: 'SF Pro', fontSize: 14.fh, color: text),
                ),
              ),
            )
          else
            ...lessons.map((lesson) {
              final isEditing = lesson.number == editingLessonNumber;
              final hColor = editingColor;
              return Padding(
                padding: po(b: 16.fh),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Padding(
                          padding: po(t: 4.fh),
                          child: Text(
                            '${lesson.number}. ',
                            style: TextStyle(fontFamily: 'Inter', fontSize: 14.fh, fontWeight: .w500, color: Color(0xff7D7D7D)),
                          ),
                        ),
                        Expanded(
                          child: Container(
                            padding: ps(v: 4.fh, h: 8.fw),
                            decoration: BoxDecoration(
                              color: isEditing ? hColor.withOpacity(0.6) : Colors.transparent,
                              border: isEditing
                                  ? Border(
                                      left: BorderSide(color: hColor, width: 2.fw),
                                      right: BorderSide(color: hColor, width: 2.fw),
                                    )
                                  : null,
                            ),
                            child: RichText(
                              text: TextSpan(
                                children: [
                                  TextSpan(
                                    text: '${lesson.subject}. ',
                                    style: TextStyle(fontFamily: 'Inter', fontSize: 14.fh, fontWeight: .w400, color: black),
                                  ),
                                  TextSpan(
                                    text: lesson.type,
                                    style: TextStyle(fontFamily: 'SF Pro', fontSize: 14.fh, fontWeight: .w400, color: black),
                                  ),
                                ],
                              ),
                            ),
                          ),
                        ),
                        SizedBox(width: 12.fw),
                        if (onEditLesson != null)
                          GestureDetector(
                            onTap: () {
                              if (onEditLesson != null) onEditLesson!(lesson);
                            },
                            child: Container(
                              width: 26.fw,
                              height: 26.fh,
                              decoration: BoxDecoration(color: loadMax, borderRadius: BorderRadius.circular(4.r)),
                              child: Icon(Icons.edit_outlined, color: Colors.white, size: 18.fh),
                            ),
                          ),
                      ],
                    ),

                    if (isEditing)
                      Row(
                        children: [
                          Spacer(),
                          Padding(
                            padding: ps(h: 30.fw),
                            child: Container(
                              decoration: BoxDecoration(color: hColor),
                              child: Text(
                                lesson.teacherName,
                                style: TextStyle(fontFamily: 'SF Pro', fontSize: 8.fh, fontWeight: .w400, color: white),
                              ),
                            ),
                          ),
                        ],
                      ),
                    Padding(
                      padding: po(t: 8.fh),
                      child: Divider(color: text.withOpacity(0.3), height: 1),
                    ),
                  ],
                ),
              );
            }),
        ],
      ),
    );
  }
}
