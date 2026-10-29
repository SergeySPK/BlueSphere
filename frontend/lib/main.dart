import 'package:flutter/material.dart';
import 'package:blue_sphere/presentation/screens/classes_screen.dart';
import 'package:blue_sphere/presentation/screens/load_screen.dart';
import 'package:blue_sphere/presentation/screens/surveys_screen.dart';
import 'package:blue_sphere/presentation/uikit/bottom_nav_bar.dart';
import 'package:blue_sphere/presentation/uikit/colors.dart';
import 'package:vize/vize.dart';
import 'package:flutter_max_miniapp/flutter_max_miniapp.dart';
import 'package:blue_sphere/data/api_service.dart';

// Точка входа в приложение
void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  try {
    final webApp = MaxWebApp();
    webApp.init();
    await webApp.enableVerticalSwipes();
  } catch (e) {
    print('Ошибка инициализации: $e');
  }

  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Blue Sphere',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(scaffoldBackgroundColor: background),
      builder: (context, child) {
        Vize.init(context, figmaWidth: 375, figmaHeight: 812);
        return child!;
      },
      home: Builder(
        builder: (context) {
          return Container(
            color: white,
            child: Center(
              child: ConstrainedBox(constraints: BoxConstraints(maxWidth: 375), child: MainScreen()),
            ),
          );
        },
      ),
    );
  }
}

class MainScreen extends StatefulWidget {
  const MainScreen({super.key});

  @override
  State<MainScreen> createState() => _MainScreenState();
}

class _MainScreenState extends State<MainScreen> {
  int _currentIndex = 0;
  String _selectedClassId = 'Выберите класс';
  String _selectedClassName = 'Выберите класс';

  @override
  Widget build(BuildContext context) {
    final List<Widget> screens = [
      ClassesScreen(
        onClassSelected: (id, name) {
          setState(() {
            _selectedClassId = id;
            _selectedClassName = name;
            _currentIndex = 1;
          });
        },
      ),

      Navigator(
        onGenerateRoute: (settings) {
          return MaterialPageRoute(
            builder: (context) => LoadScreen(classId: _selectedClassId, className: _selectedClassName, onGoToClasses: () => setState(() => _currentIndex = 0), onGoToSummary: () => setState(() => _currentIndex = 2)),
          );
        },
      ),
      SurveysScreen(classId: _selectedClassId, className: _selectedClassName, onGoToClasses: () => setState(() => _currentIndex = 0)),
    ];

    return Scaffold(
      body: IndexedStack(index: _currentIndex, children: screens),
      bottomNavigationBar: BottomNavBar(
        currentIndex: _currentIndex,
        onTap: (index) {
          setState(() {
            _currentIndex = index;
          });
        },
      ),
    );
  }
}
