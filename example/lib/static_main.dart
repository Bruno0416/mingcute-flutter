import 'package:flutter/material.dart';
import 'package:mingcute_flutter/mingcute_static.dart';

/// Optimized-size alternative: do not import the getter library in this app.
void main() => runApp(const MaterialApp(home: StaticExampleScreen()));

class StaticExampleScreen extends StatelessWidget {
  const StaticExampleScreen({super.key});

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('MingCute Icons')),
        body: const Center(
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(MingCuteRegularConst.home_1, size: 36),
              Icon(MingCuteRegularConst.search_2, size: 36),
              Icon(MingCuteFilledConst.heart, size: 36),
              Icon(MingCuteFilledConst.star, size: 36),
            ],
          ),
        ),
      );
}
