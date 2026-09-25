import { useState, useEffect, useMemo } from 'react';
import { useLocation } from 'wouter';
import { useForm, useFieldArray } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import { useGetBazaarCatalog, useCreateBazaarOrder, getListBazaarOrdersQueryKey, BazaarServiceCode } from '@workspace/api-client-react';
import { useQueryClient } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from '@/components/ui/card';
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Input } from '@/components/ui/input';
import { Separator } from '@/components/ui/separator';
import { AlertCircle, ArrowLeft, Loader2, Package, Plus, Trash2 } from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { useToast } from '@/hooks/use-toast';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '@/components/ui/command';
import { cn } from '@/lib/utils';
import { Badge } from '@/components/ui/badge';

const lineSchema = z.object({
  sku: z.string().min(1, "Please select an SKU"),
  quantity: z.coerce.number().int().min(1, "Quantity must be at least 1"),
});

const formSchema = z.object({
  warehouse_id: z.string().min(1, "Please select a warehouse"),
  service: z.enum([BazaarServiceCode.Next_Day, BazaarServiceCode.Same_Day, BazaarServiceCode.Standard]),
  lines: z.array(lineSchema).min(1, "At least one item is required"),
}).refine(data => {
  const skus = data.lines.map(l => l.sku);
  return new Set(skus).size === skus.length;
}, {
  message: "Duplicate SKUs are not allowed. Please combine quantities.",
  path: ["lines"]
});

type FormValues = z.infer<typeof formSchema>;

export default function NewOrder() {
  const [, setLocation] = useLocation();
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const { data: catalog, isLoading: isCatalogLoading, error: catalogError } = useGetBazaarCatalog();
  const createOrder = useCreateBazaarOrder();

  const [requestId, setRequestId] = useState<string>('');
  const [lastSubmittedBody, setLastSubmittedBody] = useState<string | null>(null);

  const defaultValues = useMemo(() => {
    try {
      const draft = sessionStorage.getItem('fde_bazaar_draft');
      if (draft) {
        const parsed = JSON.parse(draft);
        return parsed.values as FormValues;
      }
    } catch (e) {
      // ignore
    }
    return {
      warehouse_id: '',
      service: BazaarServiceCode.Standard,
      lines: [{ sku: '', quantity: 1 }],
    };
  }, []);

  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues,
  });

  useEffect(() => {
    try {
      const draft = sessionStorage.getItem('fde_bazaar_draft');
      if (draft) {
        const parsed = JSON.parse(draft);
        setRequestId(parsed.request_id || crypto.randomUUID());
        setLastSubmittedBody(parsed.lastSubmittedBody || null);
      } else {
        setRequestId(crypto.randomUUID());
      }
    } catch (e) {
      setRequestId(crypto.randomUUID());
    }
  }, []);

  useEffect(() => {
    const subscription = form.watch((value) => {
      if (requestId) {
        sessionStorage.setItem('fde_bazaar_draft', JSON.stringify({
          request_id: requestId,
          lastSubmittedBody,
          values: form.getValues()
        }));
      }
    });
    return () => subscription.unsubscribe();
  }, [form, requestId, lastSubmittedBody]);

  const { fields, append, remove } = useFieldArray({
    control: form.control,
    name: "lines",
  });

  const watchLines = form.watch("lines");
  const selectedWarehouse = form.watch("warehouse_id");
  const selectedService = form.watch("service");
  const selectedSkus = useMemo(() => new Set(watchLines.map(l => l?.sku).filter(Boolean)), [watchLines]);
  const selectedServiceDetails = catalog?.services.find(service => service.code === selectedService);

  const onSubmit = (values: FormValues) => {
    if (!requestId) return;

    const currentRequestId = requestId;
    const valuesString = JSON.stringify(values);

    // A lost response does not mean the server failed to save the order.
    // Recover that submission before allowing a different logical order.
    if (lastSubmittedBody && lastSubmittedBody !== valuesString) {
      form.reset(JSON.parse(lastSubmittedBody) as FormValues);
      toast({
        title: "Recover the previous submission first",
        description: "Its response was not confirmed. The original details have been restored; submit them again to recover the saved order without creating a duplicate.",
        variant: "destructive",
      });
      return;
    }

    setLastSubmittedBody(valuesString);
    sessionStorage.setItem('fde_bazaar_draft', JSON.stringify({
      request_id: currentRequestId,
      values,
      lastSubmittedBody: valuesString
    }));

    createOrder.mutate({
      data: {
        warehouse_id: values.warehouse_id,
        service: values.service,
        lines: values.lines,
        request_id: currentRequestId,
      }
    }, {
      onSuccess: (order) => {
        // Clear draft
        sessionStorage.removeItem('fde_bazaar_draft');
        if (order.delivery_status === 'sent') {
          toast({
            title: "Order Accepted",
            description: "DockSight accepted the order. Fulfillment progress is shown on the receipt.",
          });
        } else if (order.delivery_status === 'failed') {
          toast({
            title: "Order Rejected",
            description: order.last_error || "DockSight could not accept this order. Review the receipt for details.",
            variant: "destructive",
          });
        }
        queryClient.invalidateQueries({ queryKey: getListBazaarOrdersQueryKey() });
        setLocation(`/orders/${order.id}`);
      },
      onError: (error: any) => {
        // Validation rejection happens before persistence, so corrections are safe.
        // Network failures and server errors retain the original body and UUID.
        if (error.status === 422) {
          const nextRequestId = crypto.randomUUID();
          setLastSubmittedBody(null);
          setRequestId(nextRequestId);
          sessionStorage.setItem('fde_bazaar_draft', JSON.stringify({
            request_id: nextRequestId,
            values,
            lastSubmittedBody: null,
          }));
        }
        toast({
          title: "Submission Failed",
          description: typeof error.data?.detail === 'string'
            ? error.data.detail
            : error.message || "Submission was not confirmed. Retry without changing the order.",
          variant: "destructive"
        });
      }
    });
  };

  if (isCatalogLoading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (catalogError || !catalog || catalog.skus.length === 0 || catalog.warehouses.length === 0) {
    return (
      <div className="container mx-auto max-w-3xl px-4 py-8">
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Error</AlertTitle>
          <AlertDescription>
            {catalog && catalog.skus.length === 0
              ? "No SKU is available to order. Please try again later."
              : catalog && catalog.warehouses.length === 0
                ? "No warehouse is available to receive an order. Please try again later."
              : "Failed to load catalog data. Please try again later."}
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  return (
    <div className="container mx-auto max-w-4xl px-4 py-8 sm:px-6 lg:px-8">
      <div className="mb-6 flex items-center gap-4">
        <Button variant="outline" size="icon" onClick={() => setLocation('/')}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Create New Order</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Choose the warehouse that will fulfill every item in this order.
          </p>
        </div>
      </div>

      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-8">
          <div className="grid min-w-0 grid-cols-1 gap-8 md:grid-cols-2">
            <Card className="min-w-0">
              <CardHeader>
                <CardTitle>Logistics Details</CardTitle>
              </CardHeader>
              <CardContent className="space-y-6">
                <Alert>
                  <Package className="h-4 w-4" />
                  <AlertTitle>Warehouse-specific fulfillment</AlertTitle>
                  <AlertDescription>
                    DockSight will allocate zones and inventory locations within your selected warehouse.
                    Availability is checked when you submit.
                  </AlertDescription>
                </Alert>
                <FormField
                  control={form.control}
                  name="warehouse_id"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Warehouse</FormLabel>
                      <Select onValueChange={field.onChange} value={field.value}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder="Select a warehouse..." />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          {catalog.warehouses.map(warehouse => (
                            <SelectItem key={warehouse.warehouse_id} value={warehouse.warehouse_id}>
                              {warehouse.name} · {warehouse.warehouse_id}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <FormDescription>
                        Required. Items will not be moved to a different warehouse automatically.
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="service"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Service Level</FormLabel>
                      <Select onValueChange={field.onChange} value={field.value}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder="Select service..." />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          {catalog.services.map(s => (
                            <SelectItem key={s.code} value={s.code}>
                              {s.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <FormDescription>
                        {selectedServiceDetails
                          ? `${selectedServiceDetails.description} Order priority: ${selectedServiceDetails.priority}.`
                          : 'The service level determines order priority.'}
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </CardContent>
            </Card>

            <Card className="min-w-0">
              <CardHeader className="flex flex-row items-center justify-between space-y-0">
                <div>
                  <CardTitle>SKU Lines</CardTitle>
                  <CardDescription>Add items to this order.</CardDescription>
                </div>
                <Badge variant="outline">{fields.length} line(s)</Badge>
              </CardHeader>
              <CardContent className="space-y-4">
                {form.formState.errors.lines?.root && (
                  <Alert variant="destructive" className="py-2 px-3">
                    <AlertDescription>{form.formState.errors.lines.root.message}</AlertDescription>
                  </Alert>
                )}
                
                {fields.map((field, index) => (
                  <div key={field.id} className="flex items-start gap-2 relative group p-3 rounded-lg border bg-card hover:border-primary/30 transition-colors">
                    <div className="min-w-0 flex-1 space-y-3">
                      <FormField
                        control={form.control}
                        name={`lines.${index}.sku`}
                        render={({ field: skuField }) => (
                          <FormItem className="flex flex-col">
                            <FormLabel className="text-xs">SKU</FormLabel>
                            <Popover>
                              <PopoverTrigger asChild>
                                <FormControl>
                                  <Button
                                    type="button"
                                    variant="outline"
                                    role="combobox"
                                    className={cn(
                                      "w-full min-w-0 justify-between font-normal h-9",
                                      !skuField.value && "text-muted-foreground"
                                    )}
                                  >
                                    <span className="truncate">
                                      {skuField.value
                                        ? `${skuField.value} · ${catalog.skus.find((s) => s.sku === skuField.value)?.name || skuField.value}`
                                        : "Select SKU"}
                                    </span>
                                  </Button>
                                </FormControl>
                              </PopoverTrigger>
                              <PopoverContent className="w-[300px] max-w-[calc(100vw-2rem)] p-0" align="start">
                                <Command>
                                  <CommandInput placeholder="Search SKUs..." />
                                  <CommandList>
                                    <CommandEmpty>No SKU found.</CommandEmpty>
                                    <CommandGroup>
                                      {catalog.skus.map((sku) => {
                                        const isSelected = selectedSkus.has(sku.sku) && skuField.value !== sku.sku;
                                        return (
                                          <CommandItem
                                            value={`${sku.sku} ${sku.name}`}
                                            key={sku.sku}
                                            disabled={isSelected}
                                            onSelect={() => {
                                              form.setValue(`lines.${index}.sku`, sku.sku);
                                            }}
                                            className={cn(isSelected && "opacity-50")}
                                          >
                                            <div className="flex flex-col">
                                              <span className="font-medium">{sku.name}</span>
                                              <span className="text-xs font-mono text-muted-foreground">{sku.sku}</span>
                                            </div>
                                            {isSelected && (
                                              <span className="ml-auto text-xs text-destructive">Already added</span>
                                            )}
                                          </CommandItem>
                                        );
                                      })}
                                    </CommandGroup>
                                  </CommandList>
                                </Command>
                              </PopoverContent>
                            </Popover>
                            <FormMessage className="text-xs" />
                          </FormItem>
                        )}
                      />
                      <FormField
                        control={form.control}
                        name={`lines.${index}.quantity`}
                        render={({ field: qtyField }) => (
                          <FormItem>
                            <FormLabel className="text-xs">Quantity</FormLabel>
                            <FormControl>
                              <Input 
                                type="number" 
                                min={1} 
                                step={1} 
                                className="h-9 font-mono"
                                {...qtyField} 
                              />
                            </FormControl>
                            <FormMessage className="text-xs" />
                          </FormItem>
                        )}
                      />
                    </div>
                    
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 text-muted-foreground hover:text-destructive shrink-0 absolute top-2 right-2"
                      aria-label={`Remove SKU line ${index + 1}`}
                      onClick={() => remove(index)}
                      disabled={fields.length === 1}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                ))}

                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="w-full border-dashed"
                  onClick={() => append({ sku: '', quantity: 1 })}
                >
                  <Plus className="mr-2 h-4 w-4" />
                  Add Line Item
                </Button>
              </CardContent>
            </Card>
          </div>

          <div className="flex flex-wrap items-center justify-end gap-4 border-t pt-6">
            <Button 
              type="button" 
              variant="outline" 
              onClick={() => setLocation('/')}
              disabled={createOrder.isPending}
            >
              Cancel
            </Button>
            <Button 
              type="submit" 
              disabled={createOrder.isPending || fields.length === 0 || !selectedWarehouse}
              className="min-w-[120px]"
            >
              {createOrder.isPending ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Submitting
                </>
              ) : (
                "Submit Order"
              )}
            </Button>
          </div>
        </form>
      </Form>
    </div>
  );
}
