import React, { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Save, Settings2, ShieldAlert } from 'lucide-react';
import { useFulfillmentState, useUpdateConfig } from '@/hooks/use-fulfillment';
import { FulfillmentNav } from './components/FulfillmentNav';
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from '@/components/ui/card';
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Select } from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { toast } from '@/hooks/use-toast';

const configSchema = z.object({
  min_stock_threshold: z.coerce.number().min(0),
  unit_weight_kg: z.coerce.number().min(0.1),
  staging_capacity: z.coerce.number().min(1),
  manual_payload_limit_kg: z.coerce.number().min(1),
  task_duration_seconds: z.coerce
    .number()
    .int('Task duration must be a whole number of seconds')
    .min(1, 'Task duration must be at least 1 second')
    .max(86400, 'Task duration cannot exceed 86400 seconds'),
  shift: z.string().min(1)
});

export default function FulfillmentConfig() {
  const { data: state, isLoading } = useFulfillmentState();
  const updateConfig = useUpdateConfig();

  const form = useForm<z.infer<typeof configSchema>>({
    resolver: zodResolver(configSchema),
    defaultValues: {
      min_stock_threshold: 10,
      unit_weight_kg: 1,
      staging_capacity: 10,
      manual_payload_limit_kg: 25,
      task_duration_seconds: 45,
      shift: '1'
    }
  });
  const { dirtyFields } = form.formState;

  useEffect(() => {
    if (state?.config) {
      form.reset({
        min_stock_threshold: state.config.min_stock_threshold,
        unit_weight_kg: state.config.unit_weight_kg,
        staging_capacity: state.config.staging_capacity,
        manual_payload_limit_kg: state.config.manual_payload_limit_kg,
        task_duration_seconds: state.config.task_duration_seconds ?? 45,
        shift: state.config.shift
      }, {
        keepDirtyValues: true
      });
    }
  }, [state?.config, form, dirtyFields]);

  const onSubmit = async (values: z.infer<typeof configSchema>) => {
    try {
      const savedConfig = await updateConfig.mutateAsync(values);
      form.reset(savedConfig);
      toast({
        title: 'Configuration saved',
        description: 'Warehouse settings were updated successfully.'
      });
    } catch {
      // The mutation error is rendered below so server failures remain visible.
    }
  };

  if (isLoading) {
    return (
      <div className="p-6 space-y-6 max-w-3xl mx-auto">
        <FulfillmentNav active="config" />
        <Skeleton className="h-[400px] w-full" />
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6 max-w-3xl mx-auto">
      <FulfillmentNav active="config" />
      
      <div className="flex items-center gap-3 mb-6">
        <Settings2 className="h-8 w-8 text-primary" />
        <div>
          <h1 className="text-2xl font-bold tracking-tight">System Configuration</h1>
          <p className="text-muted-foreground text-sm">Adjust global planning assumptions for the POC</p>
        </div>
      </div>

      <Card>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)}>
            <CardHeader>
              <CardTitle>Optimization Parameters</CardTitle>
              <CardDescription>Changes apply to new planning runs immediately</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="grid md:grid-cols-2 gap-6">
                <FormField
                  control={form.control}
                  name="min_stock_threshold"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Legacy Min Stock Threshold — deprecated</FormLabel>
                      <FormControl>
                        <Input type="number" disabled {...field} />
                      </FormControl>
                      <FormDescription>
                        Retained for compatibility only. Low-stock alerts use each warehouse
                        SKU&apos;s predicted 7-day demand, refreshed daily at 06:00 India time.
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="staging_capacity"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Staging Capacity limit</FormLabel>
                      <FormControl>
                        <Input type="number" {...field} />
                      </FormControl>
                      <FormDescription>Max concurrent tasks per zone</FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="unit_weight_kg"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Legacy Unit Weight (kg) — deprecated</FormLabel>
                      <FormControl>
                        <Input type="number" step="0.1" disabled {...field} />
                      </FormControl>
                      <FormDescription>
                        Retained for compatibility only. Planning uses consistent positive
                        synthetic inventory weight_kg values and never falls back to this setting.
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="manual_payload_limit_kg"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Manual Payload Limit (kg)</FormLabel>
                      <FormControl>
                        <Input type="number" step="0.1" {...field} />
                      </FormControl>
                      <FormDescription>Caps manual fallback execution</FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="task_duration_seconds"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Task Duration (seconds)</FormLabel>
                      <FormControl>
                        <Input type="number" min={1} max={86400} step={1} {...field} />
                      </FormControl>
                      <FormDescription>
                        Applies to newly started tasks and replacement assignments in all stages.
                        Running tasks retain their existing timers.
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="shift"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Active Shift</FormLabel>
                      <FormControl>
                        <Select onChange={field.onChange} value={field.value}>
                          <option value="1">Shift 1</option>
                          <option value="2">Shift 2</option>
                          <option value="3">Shift 3</option>
                        </Select>
                      </FormControl>
                      <FormDescription>Affects labor availability model</FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>
              {updateConfig.isError && (
                <Alert variant="destructive">
                  <AlertTitle>Configuration could not be saved</AlertTitle>
                  <AlertDescription>{updateConfig.error.message}</AlertDescription>
                </Alert>
              )}
            </CardContent>
            <CardFooter className="flex justify-between border-t py-4 bg-muted/20">
              <Alert className="bg-transparent border-none p-0 flex items-center gap-2 max-w-[60%]">
                <ShieldAlert className="h-4 w-4 text-muted-foreground" />
                <AlertDescription className="text-xs text-muted-foreground m-0">
                  Shared POC state. Changes affect all users.
                </AlertDescription>
              </Alert>
              <Button type="submit" disabled={updateConfig.isPending}>
                <Save className="mr-2 h-4 w-4" />
                {updateConfig.isPending ? 'Saving...' : 'Save Configuration'}
              </Button>
            </CardFooter>
          </form>
        </Form>
      </Card>
    </div>
  );
}
