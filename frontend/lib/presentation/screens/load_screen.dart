import 'package:flutter/material.dart';
import 'package:vize/vize.dart';
import '../../data/api_service.dart';
import '../../domain/load_day.dart';
import '../../domain/class_status.dart';
import '../../domain/recommendation.dart';
import '../uikit/calendar.dart';
import '../uikit/colors.dart';
import '../uikit/custom_header.dart';
import '../uikit/error_screen.dart';
import '../uikit/recommendations_block.dart';
import '../uikit/status_banner.dart';
import 'day_details_screen.dart';

// Экран нагрузки
class LoadScreen extends StatefulWidget {
  final String classId;
  final String className;
  final bool isTeacher;
  final VoidCallback onGoToClasses;
  final VoidCallback onGoToSummary;

  const LoadScreen({super.key, required this.classId, required this.className, required this.onGoToClasses, required this.onGoToSummary, required this.isTeacher});

  @override
  State<LoadScreen> createState() => _LoadScreenState();
}

class _LoadScreenState extends State<LoadScreen> {
  List<LoadDay>? _loadDays;
  ClassStatus? _status;
  Recommendation? _recommendation;
  bool _isLoading = true;
  int? _errorCode;

  bool get isClassSelected => widget.classId.isNotEmpty && widget.classId != 'Выберите класс';

  @override
  void initState() {
    super.initState();
    if (isClassSelected) {
      _loadData();
    } else {
      _isLoading = false;
    }
  }

  @override
  void didUpdateWidget(covariant LoadScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.classId != widget.classId) {
      if (isClassSelected) {
        setState(() {
          _isLoading = true;
          _errorCode = null;
        });
        _loadData();
      } else {
        setState(() => _isLoading = false);
      }
    }
  }

  Future<void> _loadData() async {
    setState(() {
      _isLoading = true;
      _errorCode = null;
    });

    final now = DateTime.now();
    final month = now.month.toString().padLeft(2, '0');
    final date = "${now.day.toString().padLeft(2, '0')}.${now.month.toString().padLeft(2, '0')}";

    try {
      final heatmap = await ApiService.getHeatmap(widget.classId, month);
      if (mounted) setState(() => _loadDays = heatmap);
    } catch (e) {
      int code = 500;
      final errorString = e.toString();
      if (errorString.contains('Exception: ')) {
        code = int.tryParse(errorString.split('Exception: ')[1]) ?? 500;
      }

      if (mounted) {
        setState(() {
          _errorCode = code;
          _isLoading = false;
        });
      }
      return;
    }

    try {
      final status = await ApiService.getSummary(widget.classId, date);
      if (mounted) setState(() => _status = status);
    } catch (e) {
      print('Баннер недоступен: $e');
    }

    if (widget.isTeacher) {
      try {
        final recommendations = await ApiService.getRecommendations(widget.classId);
        if (mounted) setState(() => _recommendation = recommendations);
      } catch (e) {
        print('Рекомендации недоступны (403), скрываем их');
      }
    }

    if (mounted) {
      setState(() => _isLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: background,
      body: Column(
        children: [
          CustomHeader(title: isClassSelected ? widget.className : 'Выберите класс'),
          Expanded(child: _buildBody()),
        ],
      ),
    );
  }

  Widget _buildBody() {
    if (_errorCode != null) {
      return ErrorScreen(code: _errorCode!);
    }
    if (!isClassSelected) {
      return _buildNoClassSelected();
    }
    if (_isLoading) {
      return Center(child: CircularProgressIndicator());
    }

    return SingleChildScrollView(
      padding: po(t: 8.fh, l: 16.fw, r: 16.fw),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (_status == null)
            Center(
              child: Text('Не удалось загрузить статус', style: TextStyle(color: black)),
            )
          else
            StatusBanner(level: _status!.level ?? 4, date: _status!.date ?? '', showButton: true, onGoToSummary: widget.onGoToSummary),
          SizedBox(height: 11.fh),
          LoadCalendar(
            date: DateTime.now(),
            loadDays: _loadDays ?? [],
            onDayTap: (day) {
              final now = DateTime.now();
              final months = ['Января', 'Февраля', 'Марта', 'Апреля', 'Мая', 'Июня', 'Июля', 'Августа', 'Сентября', 'Октября', 'Ноября', 'Декабря'];
              final currentMonth = months[now.month - 1];
              final currentMonthNumber = now.month.toString();
              final dayData = _loadDays!.firstWhere((d) => d.day == day, orElse: () => LoadDay(day: day, level: 4, isEditing: false));
              Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (context) => DayDetailsScreen(
                    day: day,
                    monthName: currentMonth,
                    isTeacher: widget.isTeacher,
                    monthNumber: currentMonthNumber,
                    className: widget.className,
                    classId: widget.classId,
                    dayLevel: dayData.level,
                    bannerLevel: _status?.level ?? 4,
                    statusDate: _status?.date ?? '',
                  ),
                ),
              );
            },
          ),
          SizedBox(height: 11.fh),
          if (widget.isTeacher && _recommendation != null) RecommendationsBlock(daysToReduce: _recommendation!.daysToReduce, daysToMoveTo: _recommendation!.daysToMoveTo),
        ],
      ),
    );
  }

  Widget _buildNoClassSelected() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Text(
            'Класс не выбран',
            style: TextStyle(fontFamily: 'Inter', fontSize: 18.fh, fontWeight: .w600, color: black),
          ),
          SizedBox(height: 8.fh),
          Text(
            'Чтобы посмотреть нагрузку,\nвыберите класс',
            textAlign: TextAlign.center,
            style: TextStyle(fontFamily: 'SF Pro', fontSize: 14.fh, fontWeight: .w400, color: text),
          ),
          SizedBox(height: 24.fh),
          ElevatedButton(
            onPressed: widget.onGoToClasses,
            style: ElevatedButton.styleFrom(
              backgroundColor: bottomBarText,
              padding: ps(h: 24.fw, v: 12.fh),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12.r)),
            ),
            child: Text(
              'Перейти к классам',
              style: TextStyle(fontFamily: 'Inter', fontSize: 14.fh, fontWeight: .w500, color: white),
            ),
          ),
        ],
      ),
    );
  }
}
