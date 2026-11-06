import 'package:flutter/material.dart';
import 'package:vize/vize.dart';
import '../../domain/load_day.dart';
import 'colors.dart';

// Кастомный календарь
class LoadCalendar extends StatelessWidget {
  final DateTime date;
  final List<LoadDay> loadDays;
  final Function(int day)? onDayTap;

  const LoadCalendar({super.key, required this.date, required this.loadDays, this.onDayTap});

  Color _getLoadColor(int level) {
    switch (level) {
      case 0:
        return loadMax;
      case 1:
        return loadHigh;
      case 2:
        return loadMedium;
      case 3:
        return loadLow;
      default:
        return loadMin;
    }
  }

  String _getMonthName(int month) {
    const months = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'];
    return months[month - 1];
  }

  @override
  Widget build(BuildContext context) {
    final now = DateTime.now();
    final int daysInMonth = DateTime(date.year, date.month + 1, 0).day;
    final int firstDayWeekday = DateTime(date.year, date.month, 1).weekday;

    List<Widget> gridCells = [];

    int offset;
    int currentWeekday;

    if (firstDayWeekday == 7) {
      offset = 0;
      currentWeekday = 1;
    } else {
      offset = firstDayWeekday - 1;
      currentWeekday = firstDayWeekday;
    }

    for (int i = 0; i < offset; i++) {
      gridCells.add(_buildEmptyStartCell());
    }

    for (int day = 1; day <= daysInMonth; day++) {
      if (day == 1 && firstDayWeekday == 7) continue;
      final dayData = loadDays.firstWhere((d) => d.day == day, orElse: () => LoadDay(day: day, level: 4, isEditing: false));
      final bool isToday = (date.year == now.year) && (date.month == now.month) && (day == now.day);

      if (currentWeekday != 7) {
        gridCells.add(_buildDayCell(dayData, isToday, false));
      }
      if (currentWeekday == 7) {
        currentWeekday = 1;
      } else {
        currentWeekday++;
      }
    }

    while (gridCells.length % 6 != 0) {
      gridCells.add(_buildEmptyStartCell());
    }

    return Container(
      padding: ps(v: 16.fh, h: 16.fw),
      decoration: BoxDecoration(color: white, borderRadius: BorderRadius.circular(12)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    _getMonthName(date.month).toUpperCase(),
                    style: TextStyle(fontFamily: 'SF Pro', fontSize: 15.fh, fontWeight: .w700, color: loadMax),
                  ),
                  Text(
                    'карта нагрузки',
                    style: TextStyle(fontFamily: 'SF Pro', fontSize: 11.fh, fontWeight: .w400, color: text),
                  ),
                ],
              ),
              Spacer(),
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _buildLegendItem('чрезмерная нагрузка', loadMax),
                  SizedBox(height: 6.fh),
                  _buildLegendItem('высокая нагрузка', loadHigh),
                ],
              ),
              SizedBox(width: 11.fw),
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _buildLegendItem('средняя нагрузка', loadMedium),
                  SizedBox(height: 6.fh),
                  _buildLegendItem('небольшая нагрузка', loadLow),
                  SizedBox(height: 6.fh),
                  _buildLegendItem('минимальная нагрузка', loadMin),
                ],
              ),
            ],
          ),
          SizedBox(height: 20.fh),
          GridView.builder(
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(crossAxisCount: 6, mainAxisSpacing: 8, crossAxisSpacing: 8, childAspectRatio: 1),
            itemCount: gridCells.length,
            itemBuilder: (context, index) {
              return gridCells[index];
            },
          ),
          SizedBox(height: 8.fh),
          Row(mainAxisAlignment: MainAxisAlignment.spaceAround, children: [_buildWeekDay('пн'), _buildWeekDay('вт'), _buildWeekDay('ср'), _buildWeekDay('чт'), _buildWeekDay('пт'), _buildWeekDay('сб')]),
        ],
      ),
    );
  }

  Widget _buildEmptyStartCell() {
    return Container(
      decoration: BoxDecoration(color: Colors.transparent, borderRadius: BorderRadius.circular(5)),
    );
  }

  Widget _buildDayCell(LoadDay dayData, bool isToday, bool isSunday) {
    final level = dayData.level;
    final isEditing = dayData.isEditing;
    final fillColor = isSunday ? emptyCell : _getLoadColor(level);
    final textColor = isSunday ? text : white;

    Widget cell = Container(
      decoration: BoxDecoration(
        color: fillColor,
        borderRadius: BorderRadius.circular(5.r),
        border: isEditing
            ? Border.all(color: red, width: 3.fw)
            : isToday
            ? Border.all(color: currentDayBorder, width: 3.fw)
            : null,
      ),
      child: Stack(
        children: [
          Center(
            child: Text(
              '${dayData.day}',
              style: TextStyle(fontFamily: 'Inter', fontSize: 12.fh, fontWeight: .w400, color: textColor),
            ),
          ),
          if (isEditing)
            Positioned(
              bottom: -3,
              right: -3,
              child: Container(
                padding: pa(2),
                decoration: BoxDecoration(color: red, shape: BoxShape.circle),
                child: Icon(Icons.refresh, color: Colors.white, size: 10.fw),
              ),
            ),
        ],
      ),
    );

    if (isSunday) {
      return cell;
    }

    return GestureDetector(
      onTap: () {
        if (onDayTap != null) onDayTap!(dayData.day);
      },
      child: cell,
    );
  }

  Widget _buildLegendItem(String title, Color color) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 8.fw,
          height: 8.fh,
          decoration: BoxDecoration(color: color, shape: BoxShape.circle),
        ),
        SizedBox(width: 4.fw),
        Text(
          title,
          style: TextStyle(fontFamily: 'SF Pro', fontSize: 7.fh, fontWeight: .w400, color: black),
        ),
      ],
    );
  }

  Widget _buildWeekDay(String day) {
    return Text(
      day,
      style: TextStyle(fontFamily: 'SF Pro', fontSize: 11.fh, fontWeight: .w400, color: text),
    );
  }
}
